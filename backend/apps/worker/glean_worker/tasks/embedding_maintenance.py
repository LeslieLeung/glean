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
from glean_database.models import Entry, VectorCleanupPending
from glean_database.session import get_session_context
from glean_vector.config import (
    embedding_model_fingerprint,
    is_active_embedding_model,
    is_active_vector_backend,
    vector_backend_config,
    vector_store_fingerprint,
)

from .embedding_limits import enqueue_embedding_batch_job

logger = get_logger(__name__)

# Entries stuck in 'processing' longer than this are considered orphaned.
# Should be comfortably larger than the worker job_timeout (300s by default).
STUCK_PROCESSING_THRESHOLD = timedelta(minutes=10)
STUCK_REBUILD_PREPARING_THRESHOLD = timedelta(minutes=15)


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
    *,
    rpm: int,
    batch_size: int,
) -> int:
    """Enqueue one continuation-sized job for remaining pending entries.

    This is the safety net for the rebuild: if the initial batch of jobs
    finishes (or is lost) and pending entries remain, we enqueue more work
    so the rebuild can make progress.

    Returns:
        Number of batch jobs enqueued.
    """
    if pending <= 0:
        return 0

    queued = await enqueue_embedding_batch_job(
        redis,
        rpm=rpm,
        batch_size=batch_size,
        rebuild_id=rebuild_id,
        expected_backend=expected_backend,
        expected_store_fingerprint=expected_store_fingerprint,
        expected_model_fingerprint=expected_model_fingerprint,
        job_id_prefix=f"maint_{uuid4().hex}",
    )

    logger.info(
        "Re-enqueued batch embedding jobs from maintenance",
        extra={"pending": pending, "num_batches": queued},
    )
    return queued


async def _advance_rebuild_phase(
    session: AsyncSession,
    redis: Any,
    config: EmbeddingConfig,
) -> bool:
    """Finish the active rebuild when all article embeddings are terminal."""
    if not config.rebuild_id:
        return False

    lock = redis.lock(RedisKeys.REBUILD_LOCK_KEY, timeout=RedisKeys.REBUILD_LOCK_TIMEOUT)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        return False

    try:
        # Re-read the active generation under the rebuild lock.
        rebuild_info = await _get_rebuild_counts(session)
        if rebuild_info is None:
            return True
        current, current_counts = rebuild_info
        if current.rebuild_id != config.rebuild_id:
            return False

        if current.rebuild_phase not in (
            EmbeddingRebuildPhase.EMBEDDINGS,
            EmbeddingRebuildPhase.PREFERENCES,
        ):
            # PREPARING means collection recreation and the relational pending
            # transition have not committed yet. Never infer completion from
            # the previous generation's terminal entry statuses.
            return False

        pending = current_counts.get("pending", 0)
        processing = current_counts.get("processing", 0)
        if pending > 0 or processing > 0:
            return False

        config_service = TypedConfigService(session)
        rebuild_id = current.rebuild_id
        if rebuild_id is None:
            return False
        return await config_service.complete_rebuild(expected_rebuild_id=rebuild_id)
    finally:
        with contextlib.suppress(Exception):
            await lock.release()


async def _enqueue_idle_recovery(
    redis: Any,
    counts: dict[str, int],
    *,
    rpm: int,
    batch_size: int,
) -> int:
    """Recover pending entries during normal IDLE operation."""
    if counts.get("processing", 0) > 0:
        return 0

    pending_queued = 0
    if counts.get("pending", 0) > 0:
        acquired = await redis.set(
            RedisKeys.EMBEDDING_PENDING_MAINTENANCE_KEY,
            "1",
            ex=RedisKeys.EMBEDDING_MAINTENANCE_THROTTLE_TTL,
            nx=True,
        )
        if acquired:
            await enqueue_embedding_batch_job(
                redis,
                rpm=rpm,
                batch_size=batch_size,
                rebuild_id=None,
                job_id_prefix="idle_pending",
            )
            pending_queued = 1
    return pending_queued


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
    2. Recovers pending entries during normal IDLE operation.
    3. Re-enqueues batch jobs for remaining pending entries during a rebuild.
    4. Completes rebuilds after entry embeddings are terminal.
    """
    redis = ctx.get("redis")

    async with get_session_context() as session:
        recovered = await _recover_stuck_entries(session)

        # If in REBUILDING state, check whether we need to push more work
        # or whether the rebuild is done.
        re_enqueued = 0
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
                and config.rebuild_phase
                in (EmbeddingRebuildPhase.EMBEDDINGS, EmbeddingRebuildPhase.PREFERENCES)
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
                    rpm=config.get_rate_limit_for_provider(),
                    batch_size=config.batch_size,
                )

            if redis is not None and not failed_preparation:
                completed = await _advance_rebuild_phase(
                    session,
                    redis,
                    config,
                )
        else:
            config_service = TypedConfigService(session)
            config = await config_service.get(EmbeddingConfig)
            # Older workers cleared rebuild metadata when they opened the
            # circuit. The active generation can resume processing its pending rows.
            if (
                config.enabled
                and config.status == VectorizationStatus.ERROR
                and (config.last_error or "").startswith("Circuit breaker:")
                and is_active_vector_backend(config.vector_backend, config.vector_store_fingerprint)
                and is_active_embedding_model(
                    config.model_fingerprint,
                    provider=config.provider,
                    model=config.model,
                    dimension=config.dimension,
                    base_url=config.base_url,
                )
            ):
                resumed = await config_service.update_embedding_generation(
                    expected_version=config.version,
                    expected_rebuild_id=config.rebuild_id,
                    expected_statuses={VectorizationStatus.ERROR.value},
                    status=VectorizationStatus.IDLE,
                    last_error=None,
                    last_error_at=None,
                    error_count=0,
                )
                if resumed is not None:
                    config = resumed
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
                re_enqueued = await _enqueue_idle_recovery(
                    redis,
                    idle_counts,
                    rpm=config.get_rate_limit_for_provider(),
                    batch_size=config.batch_size,
                )
    return {
        "recovered_stuck_entries": recovered,
        "re_enqueued_batches": re_enqueued,
        "recovered_validations": recovered_validations,
        "recovered_vector_cleanups": recovered_vector_cleanups,
        "failed_stuck_preparation": failed_preparation,
        "rebuild_completed": completed,
    }
