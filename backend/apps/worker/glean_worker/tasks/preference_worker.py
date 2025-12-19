"""Preference model worker tasks."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from arq import Retry

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.session import get_session
from glean_vector.clients.milvus_client import MilvusClient
from glean_vector.services.preference_service import PreferenceService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


async def _check_vectorization_enabled(
    session: "AsyncSession",
) -> EmbeddingConfig:
    """
    Check if vectorization is enabled and healthy.

    Args:
        session: Database session

    Returns:
        EmbeddingConfig if enabled and ready

    Raises:
        Retry: If vectorization is temporarily unavailable (VALIDATING, ERROR)
        ValueError: If vectorization is permanently disabled
    """
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    # Handle different vectorization states
    if not config.enabled or config.status == VectorizationStatus.DISABLED:
        # Permanently disabled - don't retry
        raise ValueError("Vectorization is disabled")

    if config.status == VectorizationStatus.VALIDATING:
        # Temporarily validating provider - retry after 30 seconds
        logger.info("Vectorization is validating, retrying preference update in 30 seconds")
        raise Retry(defer=timedelta(seconds=30))

    if config.status == VectorizationStatus.ERROR:
        # Provider error - retry after 2 minutes to give time for recovery
        logger.warning(
            f"Vectorization in ERROR state ({config.last_error}), "
            "retrying preference update in 2 minutes"
        )
        raise Retry(defer=timedelta(minutes=2))

    if config.status in (VectorizationStatus.IDLE, VectorizationStatus.REBUILDING):
        # Working states - proceed normally
        return config

    # Unknown state - treat as temporary error
    logger.warning(f"Unknown vectorization status: {config.status}, retrying in 1 minute")
    raise Retry(defer=timedelta(minutes=1))


async def update_user_preference(
    ctx: dict[str, Any],
    user_id: str,
    entry_id: str,
    signal_type: str,
) -> dict[str, Any]:
    """
    Update user preference model after feedback.

    Args:
        ctx: Worker context
        user_id: User UUID
        entry_id: Entry UUID
        signal_type: "like", "dislike", or "bookmark"

    Returns:
        Result dictionary

    Raises:
        Retry: If vectorization is temporarily unavailable
    """
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"success": False, "user_id": user_id, "error": "Milvus unavailable"}

    # Get Redis client from worker context (provided by arq)
    redis_client = ctx.get("redis")

    async with get_session() as session:
        try:
            # Check if vectorization is enabled and get config from database
            # Raises Retry for temporary unavailability, ValueError for permanent disable
            config = await _check_vectorization_enabled(session)
        except ValueError as e:
            # Permanently disabled - return without retry
            logger.debug(f"Vectorization disabled, skipping preference update for {user_id}")
            return {"success": False, "user_id": user_id, "error": str(e)}

        # Ensure Milvus collections exist with correct model from database config
        await milvus_client.ensure_collections(
            config.dimension,
            config.provider,
            config.model,
        )

        preference_service = PreferenceService(
            db_session=session,
            milvus_client=milvus_client,
            redis_client=redis_client,
        )

        await preference_service.handle_preference_signal(
            user_id=user_id,
            entry_id=entry_id,
            signal_type=signal_type,
        )

        return {"success": True, "user_id": user_id, "signal_type": signal_type}


async def rebuild_user_preference(
    ctx: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    """
    Rebuild user preference model from scratch.

    Args:
        ctx: Worker context
        user_id: User UUID

    Returns:
        Result dictionary

    Raises:
        Retry: If vectorization is temporarily unavailable
    """
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"success": False, "user_id": user_id, "error": "Milvus unavailable"}

    # Get Redis client from worker context (provided by arq)
    redis_client = ctx.get("redis")

    async with get_session() as session:
        try:
            # Check if vectorization is enabled and get config from database
            # Raises Retry for temporary unavailability, ValueError for permanent disable
            config = await _check_vectorization_enabled(session)
        except ValueError as e:
            # Permanently disabled - return without retry
            logger.debug(f"Vectorization disabled, skipping preference rebuild for {user_id}")
            return {"success": False, "user_id": user_id, "error": str(e)}

        # Ensure Milvus collections exist with correct model from database config
        await milvus_client.ensure_collections(
            config.dimension,
            config.provider,
            config.model,
        )

        preference_service = PreferenceService(
            db_session=session,
            milvus_client=milvus_client,
            redis_client=redis_client,
        )

        await preference_service.rebuild_from_history(user_id=user_id)

        return {"success": True, "user_id": user_id}
