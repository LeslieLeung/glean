"""Embedding maintenance tasks.

Periodic housekeeping for the embedding/vectorization system:
- Recover entries stuck in 'processing' state (worker crash / job timeout)
- Re-enqueue batch jobs for remaining pending entries during a rebuild
- Auto-complete rebuild when all entries reach a terminal state
"""

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import RedisKeys, get_logger
from glean_core.schemas.config import (
    EmbeddingConfig,
    EmbeddingRebuildPhase,
    VectorizationStatus,
)
from glean_core.services import TypedConfigService
from glean_database.models import Entry, User, VectorCleanupPending
from glean_database.session import get_session_context
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)
from glean_vector.services.preference_service import get_preference_history_user_ids

from .embedding_rebuild import start_preference_rebuild_phase

logger = get_logger(__name__)

# Entries stuck in 'processing' longer than this are considered orphaned.
# Should be comfortably larger than the worker job_timeout (300s by default).
STUCK_PROCESSING_THRESHOLD = timedelta(minutes=10)
STUCK_REBUILD_PREPARING_THRESHOLD = timedelta(minutes=15)

MAINTENANCE_BATCH_SIZE = 200


async def _recover_stuck_entries(session: AsyncSession) -> int:
    """Reset entries stuck in 'processing' state back to 'pending'.

    An entry is considered stuck when it has been in 'processing' for longer
    than STUCK_PROCESSING_THRESHOLD, indicating the worker job that was
    handling it has crashed or timed out.

    Returns:
        Number of entries recovered.
    """
    threshold = datetime.now(UTC) - STUCK_PROCESSING_THRESHOLD
    cursor_result: CursorResult[Any] = await session.execute(  # type: ignore[assignment]
        update(Entry)
        .where(
            Entry.embedding_status == "processing",
            Entry.updated_at < threshold,
        )
        .values(
            embedding_status="pending",
            embedding_error="Recovered from stuck processing state",
        )
    )
    count = cursor_result.rowcount if cursor_result.rowcount else 0
    if count > 0:
        await session.commit()
        logger.info(
            "Recovered stuck embedding entries",
            extra={
                "count": count,
                "threshold_minutes": STUCK_PROCESSING_THRESHOLD.total_seconds() / 60,
            },
        )
    return count


async def _get_rebuild_counts(
    session: AsyncSession,
) -> tuple[EmbeddingConfig, dict[str, int]] | None:
    """Return (config, status_counts) when status is REBUILDING, else None."""
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    if config.status != VectorizationStatus.REBUILDING:
        return None

    result = await session.execute(
        select(Entry.embedding_status, func.count())
        .where(Entry.embedding_status.in_(["pending", "processing", "done", "failed"]))
        .group_by(Entry.embedding_status)
    )
    counts: dict[str, int] = {str(row[0]): int(row[1]) for row in result.all()}
    return config, counts


async def _re_enqueue_pending(
    redis: Any,
    pending: int,
    rebuild_id: str | None,
    expected_backend: str | None = None,
    expected_store_fingerprint: str | None = None,
    expected_model_fingerprint: str | None = None,
) -> int:
    """Enqueue batch jobs for remaining pending entries.

    This is the safety net for the rebuild: if the initial batch of jobs
    finishes (or partially fails) and pending entries remain, we enqueue
    more work so the rebuild can make progress.

    Returns:
        Number of batch jobs enqueued.
    """
    if pending <= 0:
        return 0

    num_batches = max(1, (pending + MAINTENANCE_BATCH_SIZE - 1) // MAINTENANCE_BATCH_SIZE)
    batch_prefix = f"maint_{uuid4().hex}"
    for i in range(num_batches):
        await redis.enqueue_job(
            "batch_generate_embeddings",
            MAINTENANCE_BATCH_SIZE,
            rebuild_id,
            expected_backend,
            expected_store_fingerprint,
            expected_model_fingerprint,
            _job_id=f"{batch_prefix}_{i}",
        )

    logger.info(
        "Re-enqueued batch embedding jobs from maintenance",
        extra={"pending": pending, "num_batches": num_batches},
    )
    return num_batches


async def _recover_preference_phase(
    session: AsyncSession,
    redis: Any,
    config: EmbeddingConfig,
) -> int:
    """Re-enqueue pending preference users after an interrupted phase."""
    if not config.rebuild_id:
        return 0
    pending_key = RedisKeys.rebuild_preferences(config.rebuild_id)
    pending_members = await redis.smembers(pending_key)
    user_ids = [
        member.decode() if isinstance(member, bytes) else str(member) for member in pending_members
    ]

    # Redis may have restarted after the DB phase was committed. Rebuild the
    # pending set from durable history; recalculation is idempotent.
    if not user_ids:
        user_ids = await get_preference_history_user_ids(session)
        if not user_ids:
            config_service = TypedConfigService(session)
            await config_service.complete_rebuild(expected_rebuild_id=config.rebuild_id)
            return 0
        await redis.sadd(pending_key, *user_ids)

    await redis.expire(pending_key, RedisKeys.REBUILD_PREFERENCES_TTL)
    for user_id in user_ids:
        await redis.enqueue_job(
            "rebuild_user_preference",
            user_id,
            config.rebuild_id,
            config.vector_backend,
            config.vector_store_fingerprint,
            config.model_fingerprint,
            _job_id=f"rebuild_pref_{config.rebuild_id}_{user_id}",
        )
    return len(user_ids)


async def _advance_rebuild_phase(
    session: AsyncSession,
    redis: Any,
    config: EmbeddingConfig,
) -> tuple[bool, int]:
    """Advance terminal embeddings into the preference phase under a lock."""
    if not config.rebuild_id:
        return False, 0

    lock = redis.lock(RedisKeys.REBUILD_LOCK_KEY, timeout=RedisKeys.REBUILD_LOCK_TIMEOUT)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        return False, 0

    try:
        # A preference worker may have completed the generation while we
        # waited for the lock. Re-read before changing phase state.
        rebuild_info = await _get_rebuild_counts(session)
        if rebuild_info is None:
            return True, 0
        current, current_counts = rebuild_info
        if current.rebuild_id != config.rebuild_id:
            return False, 0

        if current.rebuild_phase == EmbeddingRebuildPhase.PREFERENCES:
            queued = await _recover_preference_phase(session, redis, current)
            return False, queued
        if current.rebuild_phase != EmbeddingRebuildPhase.EMBEDDINGS:
            # PREPARING means collection recreation and the relational pending
            # transition have not committed yet. Never infer completion from
            # the previous generation's terminal entry statuses.
            return False, 0

        pending = current_counts.get("pending", 0)
        processing = current_counts.get("processing", 0)
        if pending > 0 or processing > 0:
            return False, 0

        config_service = TypedConfigService(session)
        rebuild_id = current.rebuild_id
        if rebuild_id is None:
            return False, 0
        queued = await start_preference_rebuild_phase(
            session,
            redis,
            config_service,
            rebuild_id,
        )
        completed = queued == 0
        return completed, queued
    finally:
        with contextlib.suppress(Exception):
            await lock.release()


async def _enqueue_idle_recovery(
    redis: Any,
    counts: dict[str, int],
) -> tuple[int, int]:
    """Recover pending/failed entries during normal IDLE operation."""
    if counts.get("processing", 0) > 0:
        return 0, 0

    pending_queued = 0
    failed_queued = 0
    if counts.get("pending", 0) > 0:
        acquired = await redis.set(
            RedisKeys.EMBEDDING_PENDING_MAINTENANCE_KEY,
            "1",
            ex=RedisKeys.EMBEDDING_MAINTENANCE_THROTTLE_TTL,
            nx=True,
        )
        if acquired:
            await redis.enqueue_job(
                "batch_generate_embeddings",
                MAINTENANCE_BATCH_SIZE,
                None,
            )
            pending_queued = 1

    if counts.get("failed", 0) > 0:
        acquired = await redis.set(
            RedisKeys.EMBEDDING_FAILED_MAINTENANCE_KEY,
            "1",
            ex=RedisKeys.EMBEDDING_MAINTENANCE_THROTTLE_TTL,
            nx=True,
        )
        if acquired:
            await redis.enqueue_job(
                "retry_failed_embeddings",
                MAINTENANCE_BATCH_SIZE,
            )
            failed_queued = 1
    return pending_queued, failed_queued


async def _enqueue_pending_preference_users(
    session: AsyncSession,
    redis: Any,
) -> int:
    """Retry preference users from Redis and the durable revision outbox."""
    members = await redis.smembers(RedisKeys.PREFERENCE_PENDING_USERS_KEY)
    user_ids = {member.decode() if isinstance(member, bytes) else str(member) for member in members}
    durable_result = await session.execute(
        select(User.id).where(User.preference_revision > User.preference_synced_revision)
    )
    user_ids.update(str(row[0]) for row in durable_result.all())
    if user_ids:
        await redis.sadd(RedisKeys.PREFERENCE_PENDING_USERS_KEY, *user_ids)

    prefix = f"pref_recover_{uuid4().hex}"
    for index, user_id in enumerate(sorted(user_ids)):
        await redis.enqueue_job(
            "rebuild_user_preference",
            user_id,
            _job_id=f"{prefix}_{index}",
        )
    return len(user_ids)


async def _enqueue_validation_recovery(redis: Any, config: EmbeddingConfig) -> int:
    """Recover a VALIDATING generation whose original enqueue/job was lost."""
    if (
        config.version is None
        or config.target_vector_backend is None
        or config.target_vector_store_fingerprint is None
        or config.target_model_fingerprint is None
    ):
        return 0

    runtime_backend = vector_backend_config.backend.lower()
    runtime_store_fingerprint = vector_store_fingerprint()
    runtime_model_fingerprint = embedding_model_fingerprint(
        config.provider,
        config.model,
        config.dimension,
        config.base_url,
    )
    if (
        config.target_vector_backend.lower() != runtime_backend
        or config.target_vector_store_fingerprint != runtime_store_fingerprint
        or config.target_model_fingerprint != runtime_model_fingerprint
    ):
        return 0

    acquired = await redis.set(
        RedisKeys.embedding_validation_maintenance(config.version),
        "1",
        ex=RedisKeys.EMBEDDING_MAINTENANCE_THROTTLE_TTL,
        nx=True,
    )
    if not acquired:
        return 0

    await redis.enqueue_job(
        "validate_and_rebuild_embeddings",
        force_rebuild=config.target_force_rebuild,
        expected_version=config.version,
        expected_backend=config.target_vector_backend,
        expected_store_fingerprint=config.target_vector_store_fingerprint,
        expected_model_fingerprint=config.target_model_fingerprint,
        _job_id=f"validate_embedding_recovery_{config.version}_{uuid4().hex}",
    )
    return 1


async def _enqueue_vector_cleanup_recovery(
    session: AsyncSession,
    redis: Any,
) -> int:
    """Recover cleanup jobs committed before Redis enqueue was available."""
    result = await session.execute(
        select(
            VectorCleanupPending.entry_id,
            VectorCleanupPending.feed_id,
        )
        .order_by(VectorCleanupPending.created_at)
        .limit(1_000)
    )
    by_feed: dict[str, list[str]] = {}
    for entry_id, feed_id in result.all():
        by_feed.setdefault(str(feed_id), []).append(str(entry_id))

    queued = 0
    for feed_id, entry_ids in by_feed.items():
        acquired = await redis.set(
            RedisKeys.vector_cleanup_maintenance(feed_id),
            "1",
            ex=RedisKeys.EMBEDDING_MAINTENANCE_THROTTLE_TTL,
            nx=True,
        )
        if not acquired:
            continue
        await redis.enqueue_job(
            "cleanup_orphan_embeddings",
            feed_id,
            entry_ids,
            _job_id=f"cleanup_recovery_{feed_id}_{uuid4().hex}",
        )
        queued += 1
    return queued


async def _fail_stuck_rebuild_preparation(
    session: AsyncSession,
    config: EmbeddingConfig,
) -> bool:
    """Turn an abandoned PREPARING phase into an explicit recoverable error."""
    if (
        config.rebuild_phase != EmbeddingRebuildPhase.PREPARING
        or config.rebuild_started_at is None
        or config.rebuild_id is None
        or datetime.now(UTC) - config.rebuild_started_at < STUCK_REBUILD_PREPARING_THRESHOLD
    ):
        return False

    updated = await TypedConfigService(session).update_embedding_generation(
        expected_version=config.version,
        expected_rebuild_id=config.rebuild_id,
        expected_statuses={VectorizationStatus.REBUILDING.value},
        status=VectorizationStatus.ERROR,
        last_error="Embedding rebuild preparation was interrupted; run a full rebuild",
        last_error_at=datetime.now(UTC),
        error_count=config.error_count + 1,
        target_vector_backend=None,
        target_vector_store_fingerprint=None,
        target_model_fingerprint=None,
        target_force_rebuild=False,
        rebuild_id=None,
        rebuild_started_at=None,
        rebuild_phase=None,
    )
    return updated is not None


async def scheduled_embedding_maintenance(ctx: dict[str, Any]) -> dict[str, Any]:
    """Periodic maintenance for the embedding system.

    Runs as an arq cron job. Performs four checks:
    1. Recovers entries stuck in 'processing' (worker crash / timeout).
    2. Recovers pending/failed entries during normal IDLE operation.
    3. Re-enqueues batch jobs for remaining pending entries during a rebuild.
    4. Starts preference rebuilds only after entry embeddings are terminal.
    """
    redis = ctx.get("redis")

    async with get_session_context() as session:
        recovered = await _recover_stuck_entries(session)

        # If in REBUILDING state, check whether we need to push more work
        # or whether the rebuild is done.
        re_enqueued = 0
        retried_failed = 0
        queued_preferences = 0
        recovered_preference_users = 0
        recovered_validations = 0
        recovered_vector_cleanups = 0
        failed_preparation = False
        completed = False
        if redis is not None:
            recovered_vector_cleanups = await _enqueue_vector_cleanup_recovery(
                session,
                redis,
            )
        rebuild_info = await _get_rebuild_counts(session)
        if rebuild_info is not None:
            config, counts = rebuild_info
            pending = counts.get("pending", 0)
            processing = counts.get("processing", 0)
            failed_preparation = await _fail_stuck_rebuild_preparation(
                session,
                config,
            )

            if (
                not failed_preparation
                and config.rebuild_phase == EmbeddingRebuildPhase.EMBEDDINGS
                and pending > 0
                and processing == 0
                and redis is not None
            ):
                re_enqueued = await _re_enqueue_pending(
                    redis,
                    pending,
                    config.rebuild_id,
                    config.vector_backend,
                    config.vector_store_fingerprint,
                    config.model_fingerprint,
                )

            if redis is not None and not failed_preparation:
                completed, queued_preferences = await _advance_rebuild_phase(
                    session,
                    redis,
                    config,
                )
        else:
            config_service = TypedConfigService(session)
            config = await config_service.get(EmbeddingConfig)
            if (
                redis is not None
                and config.enabled
                and config.status == VectorizationStatus.VALIDATING
            ):
                recovered_validations = await _enqueue_validation_recovery(
                    redis,
                    config,
                )
            if redis is not None and config.enabled and config.status == VectorizationStatus.IDLE:
                count_result = await session.execute(
                    select(Entry.embedding_status, func.count())
                    .where(Entry.embedding_status.in_(["pending", "processing", "done", "failed"]))
                    .group_by(Entry.embedding_status)
                )
                idle_counts = {str(row[0]): int(row[1]) for row in count_result.all()}
                re_enqueued, retried_failed = await _enqueue_idle_recovery(
                    redis,
                    idle_counts,
                )
                recovered_preference_users = await _enqueue_pending_preference_users(
                    session,
                    redis,
                )

    return {
        "recovered_stuck_entries": recovered,
        "re_enqueued_batches": re_enqueued,
        "retried_failed_batches": retried_failed,
        "queued_preference_rebuilds": queued_preferences,
        "recovered_preference_users": recovered_preference_users,
        "recovered_validations": recovered_validations,
        "recovered_vector_cleanups": recovered_vector_cleanups,
        "failed_stuck_preparation": failed_preparation,
        "rebuild_completed": completed,
    }
