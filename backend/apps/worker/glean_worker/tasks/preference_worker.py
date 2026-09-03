"""Preference model worker tasks."""

import contextlib
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from arq import Retry
from sqlalchemy import select, update

from glean_core import RedisKeys, get_logger
from glean_core.schemas.config import (
    EmbeddingConfig,
    EmbeddingRebuildPhase,
    VectorizationStatus,
)
from glean_core.services import TypedConfigService
from glean_database.models import User
from glean_database.session import get_session_context
from glean_vector.config import (
    embedding_model_fingerprint,
    is_active_embedding_model,
    is_active_vector_backend,
    vector_backend_config,
    vector_store_fingerprint,
)
from glean_vector.services.preference_service import (
    PreferenceEmbeddingsNotReadyError,
    PreferenceService,
    get_preference_history_user_ids,
)

from ._vector_client import ensure_vector_client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class StalePreferenceGenerationError(RuntimeError):
    """The preference job belongs to an obsolete embedding generation."""


async def _mark_user_pending(redis: Any | None, user_id: str) -> None:
    if redis is not None:
        await redis.sadd(RedisKeys.PREFERENCE_PENDING_USERS_KEY, user_id)


async def _run_rebuild_with_generation_fence(
    *,
    redis: Any,
    session: "AsyncSession",
    service: PreferenceService,
    user_id: str,
    expected_version: str | None,
    expected_rebuild_id: str | None,
    allow_failed_embeddings: bool,
) -> None:
    """Serialize preference replacement against collection recreation."""
    lock = redis.lock(
        RedisKeys.REBUILD_LOCK_KEY,
        timeout=RedisKeys.REBUILD_LOCK_TIMEOUT,
        blocking_timeout=RedisKeys.REBUILD_LOCK_TIMEOUT,
    )
    acquired = await lock.acquire()
    if not acquired:
        raise Retry(defer=timedelta(seconds=5))

    try:
        session.expire_all()
        current = await TypedConfigService(session).get(EmbeddingConfig)
        if current.version != expected_version:
            raise StalePreferenceGenerationError("Embedding config version changed")
        if expected_rebuild_id is None:
            if current.status != VectorizationStatus.IDLE:
                raise StalePreferenceGenerationError("Normal preference job is no longer IDLE")
        elif (
            current.status != VectorizationStatus.REBUILDING
            or current.rebuild_id != expected_rebuild_id
            or current.rebuild_phase != EmbeddingRebuildPhase.PREFERENCES
        ):
            raise StalePreferenceGenerationError("Preference rebuild generation changed")
        if not is_active_vector_backend(
            current.vector_backend,
            current.vector_store_fingerprint,
        ) or not is_active_embedding_model(
            current.model_fingerprint,
            provider=current.provider,
            model=current.model,
            dimension=current.dimension,
            base_url=current.base_url,
        ):
            raise StalePreferenceGenerationError("Active vector backend changed")

        # Claim the generic dirty marker before rebuilding. A new signal that
        # arrives during this critical section re-adds it and will therefore
        # survive this job's successful completion.
        await redis.srem(RedisKeys.PREFERENCE_PENDING_USERS_KEY, user_id)
        preference_revision = await session.scalar(
            select(User.preference_revision).where(User.id == user_id)
        )
        if preference_revision is None:
            raise StalePreferenceGenerationError("Preference user no longer exists")
        await service.rebuild_from_history(
            user_id=user_id,
            allow_failed_embeddings=allow_failed_embeddings,
        )
        # The history rebuild commits internally. Advance only to the revision
        # captured before it began; any concurrent signal leaves revision >
        # synced_revision and maintenance will enqueue another rebuild.
        await session.execute(
            update(User)
            .where(
                User.id == user_id,
                User.preference_synced_revision < preference_revision,
            )
            .values(preference_synced_revision=preference_revision)
        )
        await session.commit()
    except Exception:
        await _mark_user_pending(redis, user_id)
        raise
    finally:
        with contextlib.suppress(Exception):
            await lock.release()


async def _check_vectorization_enabled(
    session: "AsyncSession",
    *,
    expected_rebuild_id: str | None = None,
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

    if not is_active_vector_backend(
        config.vector_backend,
        config.vector_store_fingerprint,
    ) or not is_active_embedding_model(
        config.model_fingerprint,
        provider=config.provider,
        model=config.model,
        dimension=config.dimension,
        base_url=config.base_url,
    ):
        logger.info(
            "Vector backend transition is pending; retrying preference update",
            extra={
                "stored_backend": config.vector_backend,
                "runtime_backend": vector_backend_config.backend,
            },
        )
        raise Retry(defer=timedelta(seconds=30))

    if expected_rebuild_id is not None:
        if (
            config.status == VectorizationStatus.REBUILDING
            and config.rebuild_id == expected_rebuild_id
            and config.rebuild_phase == EmbeddingRebuildPhase.PREFERENCES
        ):
            return config
        raise ValueError("Preference rebuild generation is stale")

    if config.status == VectorizationStatus.IDLE:
        return config

    if config.status == VectorizationStatus.REBUILDING:
        logger.info("Embedding rebuild is not ready for preference updates; retrying")
        raise Retry(defer=timedelta(seconds=30))

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
    redis_client = ctx.get("redis")
    await _mark_user_pending(redis_client, user_id)

    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        error = "Vector backend unavailable"
        if vector_error:
            error = f"{error}: {vector_error}"
        raise Retry(defer=timedelta(seconds=30)) from RuntimeError(error)

    async with get_session_context() as session:
        try:
            # Check if vectorization is enabled and get config from database
            # Raises Retry for temporary unavailability, ValueError for permanent disable
            config = await _check_vectorization_enabled(session)
        except ValueError as e:
            # Permanently disabled - return without retry
            logger.debug(f"Vectorization disabled, skipping preference update for {user_id}")
            return {"success": False, "user_id": user_id, "error": str(e)}

        # Ensure vector storage exists with correct model from database config
        await vector_client.ensure_collections(
            config.dimension,
            config.provider,
            config.model,
        )

        preference_service = PreferenceService(
            db_session=session,
            vector_client=vector_client,
            redis_client=redis_client,
        )

        try:
            if redis_client is None:
                raise RuntimeError("Redis unavailable for preference generation fence")
            await _run_rebuild_with_generation_fence(
                redis=redis_client,
                session=session,
                service=preference_service,
                user_id=user_id,
                expected_version=config.version,
                expected_rebuild_id=None,
                allow_failed_embeddings=False,
            )
        except PreferenceEmbeddingsNotReadyError as error:
            if redis_client is not None:
                await redis_client.sadd(RedisKeys.PREFERENCE_PENDING_USERS_KEY, user_id)
            logger.info(
                "Preference signal is waiting for entry embeddings",
                extra={"user_id": user_id, "entry_count": len(error.entry_ids)},
            )
            raise Retry(defer=timedelta(seconds=30)) from error

        return {"success": True, "user_id": user_id, "signal_type": signal_type}


async def rebuild_user_preference(
    ctx: dict[str, Any],
    user_id: str,
    rebuild_id: str | None = None,
    expected_backend: str | None = None,
    expected_store_fingerprint: str | None = None,
    expected_model_fingerprint: str | None = None,
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
    if (
        expected_backend is not None
        and expected_backend.lower() != vector_backend_config.backend.lower()
    ):
        raise Retry(defer=timedelta(seconds=15))
    if (
        expected_store_fingerprint is not None
        and expected_store_fingerprint != vector_store_fingerprint()
    ):
        raise Retry(defer=timedelta(seconds=15))

    redis_client = ctx.get("redis")
    await _mark_user_pending(redis_client, user_id)

    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        error = "Vector backend unavailable"
        if vector_error:
            error = f"{error}: {vector_error}"
        raise Retry(defer=timedelta(seconds=30)) from RuntimeError(error)

    async with get_session_context() as session:
        try:
            # Check if vectorization is enabled and get config from database
            # Raises Retry for temporary unavailability, ValueError for permanent disable
            config = await _check_vectorization_enabled(
                session,
                expected_rebuild_id=rebuild_id,
            )
        except ValueError as e:
            # Permanently disabled - return without retry
            logger.debug(f"Vectorization disabled, skipping preference rebuild for {user_id}")
            return {"success": False, "user_id": user_id, "error": str(e)}
        if expected_model_fingerprint is not None and expected_model_fingerprint != (
            embedding_model_fingerprint(
                config.provider,
                config.model,
                config.dimension,
                config.base_url,
            )
        ):
            return {
                "success": False,
                "user_id": user_id,
                "skipped": "stale embedding model",
            }

        # Ensure vector storage exists with correct model from database config
        await vector_client.ensure_collections(
            config.dimension,
            config.provider,
            config.model,
        )

        preference_service = PreferenceService(
            db_session=session,
            vector_client=vector_client,
            redis_client=redis_client,
        )

        try:
            if redis_client is None:
                raise RuntimeError("Redis unavailable for preference generation fence")
            await _run_rebuild_with_generation_fence(
                redis=redis_client,
                session=session,
                service=preference_service,
                user_id=user_id,
                expected_version=config.version,
                expected_rebuild_id=rebuild_id,
                allow_failed_embeddings=rebuild_id is not None,
            )
        except PreferenceEmbeddingsNotReadyError as error:
            if redis_client is not None:
                await redis_client.sadd(RedisKeys.PREFERENCE_PENDING_USERS_KEY, user_id)
            logger.info(
                "Preference history is waiting for entry embeddings",
                extra={"user_id": user_id, "entry_count": len(error.entry_ids)},
            )
            raise Retry(defer=timedelta(seconds=30)) from error

        # Persist the DB half of the model before advertising this user as
        # complete. A retry remains safe because history rebuild is idempotent.
        await session.commit()
        if rebuild_id is not None:
            await _mark_rebuild_user_complete(ctx, session, rebuild_id, user_id)

        return {"success": True, "user_id": user_id}


async def _mark_rebuild_user_complete(
    ctx: dict[str, Any],
    session: "AsyncSession",
    rebuild_id: str,
    user_id: str,
) -> None:
    """Remove one pending user and finish the matching rebuild at zero."""
    redis = ctx.get("redis")
    if redis is None:
        raise RuntimeError("Redis unavailable while completing preference rebuild")

    lock = redis.lock(RedisKeys.REBUILD_LOCK_KEY, timeout=RedisKeys.REBUILD_LOCK_TIMEOUT)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        raise Retry(defer=timedelta(seconds=5))

    try:
        config_service = TypedConfigService(session)
        current = await config_service.get(EmbeddingConfig)
        if (
            current.status != VectorizationStatus.REBUILDING
            or current.rebuild_id != rebuild_id
            or current.rebuild_phase != EmbeddingRebuildPhase.PREFERENCES
        ):
            return

        pending_key = RedisKeys.rebuild_preferences(rebuild_id)
        if not bool(await redis.exists(pending_key)):
            # A Redis restart/eviction must not make a missing set look like an
            # empty, completed phase. Reconstruct the conservative pending set
            # from durable history; recalculation is idempotent.
            history_user_ids = await get_preference_history_user_ids(session)
            if history_user_ids:
                await redis.sadd(pending_key, *history_user_ids)
                await redis.expire(
                    pending_key,
                    RedisKeys.REBUILD_PREFERENCES_TTL,
                )
        await redis.srem(pending_key, user_id)
        remaining = int(await redis.scard(pending_key))
        if remaining == 0:
            await config_service.complete_rebuild(expected_rebuild_id=rebuild_id)
            await redis.delete(pending_key)
            logger.info(
                "Embedding and preference rebuild completed",
                extra={"rebuild_id": rebuild_id},
            )
    finally:
        with contextlib.suppress(Exception):
            await lock.release()
