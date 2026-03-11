"""Embedding maintenance tasks.

Periodic housekeeping for the embedding/vectorization system:
- Recover entries stuck in 'processing' state (worker crash / job timeout)
- Re-enqueue batch jobs for remaining pending entries during a rebuild
- Auto-complete rebuild when all entries reach a terminal state
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.models import Entry
from glean_database.session import get_session_context

logger = get_logger(__name__)

# Entries stuck in 'processing' longer than this are considered orphaned.
# Should be comfortably larger than the worker job_timeout (300s by default).
STUCK_PROCESSING_THRESHOLD = timedelta(minutes=10)

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


async def _re_enqueue_pending(redis: Any, pending: int) -> int:
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
            _job_id=f"{batch_prefix}_{i}",
        )

    logger.info(
        "Re-enqueued batch embedding jobs from maintenance",
        extra={"pending": pending, "num_batches": num_batches},
    )
    return num_batches


async def _check_rebuild_completion(session: AsyncSession) -> bool:
    """Check if REBUILDING state should transition to IDLE.

    The rebuild is complete when no entries remain in 'pending' or 'processing'
    state — i.e. every entry has reached a terminal state ('done' or 'failed').

    Returns:
        True if rebuild was completed by this call.
    """
    rebuild_info = await _get_rebuild_counts(session)
    if rebuild_info is None:
        return False

    _config, counts = rebuild_info
    pending = counts.get("pending", 0)
    processing = counts.get("processing", 0)
    done = counts.get("done", 0)
    failed = counts.get("failed", 0)

    if pending > 0 or processing > 0:
        logger.debug(
            "Rebuild still in progress",
            extra={"pending": pending, "processing": processing},
        )
        return False

    if (done + failed) == 0:
        return False

    config_service = TypedConfigService(session)
    await config_service.complete_rebuild()
    logger.info(
        "Rebuild completed automatically by maintenance cron",
        extra={"done": done, "failed": failed},
    )
    return True


async def scheduled_embedding_maintenance(ctx: dict[str, Any]) -> dict[str, Any]:
    """Periodic maintenance for the embedding system.

    Runs as an arq cron job. Performs three checks:
    1. Recovers entries stuck in 'processing' (worker crash / timeout).
    2. Re-enqueues batch jobs for remaining pending entries during a rebuild.
    3. Transitions REBUILDING -> IDLE when all entries are processed.
    """
    redis = ctx.get("redis")

    async with get_session_context() as session:
        recovered = await _recover_stuck_entries(session)

        # If in REBUILDING state, check whether we need to push more work
        # or whether the rebuild is done.
        re_enqueued = 0
        rebuild_info = await _get_rebuild_counts(session)
        if rebuild_info is not None:
            _config, counts = rebuild_info
            pending = counts.get("pending", 0)
            processing = counts.get("processing", 0)

            if pending > 0 and processing == 0 and redis is not None:
                re_enqueued = await _re_enqueue_pending(redis, pending)

        completed = await _check_rebuild_completion(session)

    return {
        "recovered_stuck_entries": recovered,
        "re_enqueued_batches": re_enqueued,
        "rebuild_completed": completed,
    }
