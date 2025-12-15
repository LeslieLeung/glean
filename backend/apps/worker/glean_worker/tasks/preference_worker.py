"""Preference model worker tasks."""

from typing import TYPE_CHECKING, Any

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
) -> tuple[bool, EmbeddingConfig]:
    """
    Check if vectorization is enabled and healthy.

    Args:
        session: Database session

    Returns:
        Tuple of (is_enabled, config)
    """
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    # Check if enabled and in a working state
    is_enabled = config.enabled and config.status in (
        VectorizationStatus.IDLE,
        VectorizationStatus.REBUILDING,
    )

    return is_enabled, config


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
    """
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"success": False, "user_id": user_id, "error": "Milvus unavailable"}

    async for session in get_session():
        # Check if vectorization is enabled and get config from database
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug(f"Vectorization disabled, skipping preference update for {user_id}")
            return {"success": False, "user_id": user_id, "error": "Vectorization disabled"}

        # Ensure Milvus collections exist with correct model from database config
        milvus_client.ensure_collections(
            config.dimension,
            config.provider,
            config.model,
        )

        preference_service = PreferenceService(
            db_session=session,
            milvus_client=milvus_client,
        )

        await preference_service.handle_preference_signal(
            user_id=user_id,
            entry_id=entry_id,
            signal_type=signal_type,
        )

        # Session will auto-commit when exiting get_session() context
        break

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
    """
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"success": False, "user_id": user_id, "error": "Milvus unavailable"}

    async for session in get_session():
        # Check if vectorization is enabled and get config from database
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug(f"Vectorization disabled, skipping preference rebuild for {user_id}")
            return {"success": False, "user_id": user_id, "error": "Vectorization disabled"}

        # Ensure Milvus collections exist with correct model from database config
        milvus_client.ensure_collections(
            config.dimension,
            config.provider,
            config.model,
        )

        preference_service = PreferenceService(
            db_session=session,
            milvus_client=milvus_client,
        )

        await preference_service.rebuild_from_history(user_id=user_id)

        # Session will auto-commit when exiting get_session() context
        break

    return {"success": True, "user_id": user_id}
