"""Embedding rebuild task."""

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from arq import Retry
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.redis_keys import RedisKeys
from glean_core.schemas.config import (
    EmbeddingConfig,
    EmbeddingRebuildPhase,
    VectorizationStatus,
)
from glean_core.services import TypedConfigService
from glean_database.models import Entry, UserPreferenceStats
from glean_database.session import get_session_context
from glean_vector.config import EmbeddingConfig as EmbeddingSettings
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)
from glean_vector.services.preference_service import get_preference_history_user_ids

from ._vector_client import ensure_vector_client

logger = get_logger(__name__)

REBUILD_BATCH_SIZE = 200


class StaleEmbeddingRebuildError(RuntimeError):
    """The destructive rebuild no longer owns the active config generation."""


class EmbeddingRebuildExecutionError(RuntimeError):
    """Carry generation identity when a rebuild fails after it has started."""

    def __init__(
        self,
        error: Exception,
        *,
        version: str | None,
        rebuild_id: str,
    ) -> None:
        self.original_error = error
        self.version = version
        self.rebuild_id = rebuild_id
        super().__init__(str(error))


async def _find_duplicate_entry_ids(session: AsyncSession) -> list[str]:
    """Return entry IDs that belong to duplicate (feed_id, guid) groups."""
    duplicate_pairs = (
        select(Entry.feed_id, Entry.guid)
        .where(Entry.guid.is_not(None))
        .group_by(Entry.feed_id, Entry.guid)
        .having(func.count(Entry.id) > 1)
        .subquery()
    )

    duplicate_ids_result = await session.execute(
        select(Entry.id)
        .join(
            duplicate_pairs,
            (Entry.feed_id == duplicate_pairs.c.feed_id) & (Entry.guid == duplicate_pairs.c.guid),
        )
        .order_by(Entry.feed_id, Entry.guid, Entry.created_at, Entry.id)
    )
    return [row[0] for row in duplicate_ids_result.all()]


async def rebuild_embeddings(
    ctx: dict[str, Any],
    config: dict[str, Any] | None = None,
    expected_version: str | None = None,
    expected_backend: str | None = None,
    expected_store_fingerprint: str | None = None,
    expected_model_fingerprint: str | None = None,
) -> dict[str, Any]:
    """
    Rebuild embeddings after config change.

    Steps:
      1) Load the validated typed embedding config generation
      2) Update status to REBUILDING
      3) Recreate vector collections if dimension changed
      4) Mark all entries pending
      5) Enqueue embedding jobs in batches
      6) Keep status in the embedding phase until maintenance sees terminal entries
      7) Rebuild preferences from durable history, then transition to IDLE
    """
    runtime_backend = vector_backend_config.backend.lower()
    runtime_store_fingerprint = vector_store_fingerprint()
    if expected_backend is not None and expected_backend.lower() != runtime_backend:
        raise Retry(defer=timedelta(seconds=15))
    if (
        expected_store_fingerprint is not None
        and expected_store_fingerprint != runtime_store_fingerprint
    ):
        raise Retry(defer=timedelta(seconds=15))

    async with get_session_context() as session:
        current = await TypedConfigService(session).get(EmbeddingConfig)
        if expected_version is not None and current.version != expected_version:
            return {"success": False, "skipped": "stale config version"}
        target_backend = current.target_vector_backend or expected_backend
        target_store_fingerprint = (
            current.target_vector_store_fingerprint or expected_store_fingerprint
        )
        target_model_fingerprint = current.target_model_fingerprint or expected_model_fingerprint
        if target_backend is not None and target_backend.lower() != runtime_backend:
            raise Retry(defer=timedelta(seconds=15))
        if (
            target_store_fingerprint is not None
            and target_store_fingerprint != runtime_store_fingerprint
        ):
            raise Retry(defer=timedelta(seconds=15))
        runtime_model_fingerprint = embedding_model_fingerprint(
            current.provider,
            current.model,
            current.dimension,
            current.base_url,
        )
        if (
            target_model_fingerprint is not None
            and target_model_fingerprint != runtime_model_fingerprint
        ):
            return {"success": False, "skipped": "stale embedding model"}

    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        error = RuntimeError(
            f"Vector backend unavailable: {vector_error}"
            if vector_error
            else "Vector backend unavailable"
        )
        await _mark_rebuild_error_for_version(error, expected_version=expected_version)
        if vector_error:
            return {"success": False, "error": f"Vector backend unavailable: {vector_error}"}
        return {"success": False, "error": "Vector backend unavailable"}

    redis = ctx.get("redis")
    if not redis:
        await _mark_rebuild_error_for_version(
            RuntimeError("Redis unavailable"),
            expected_version=expected_version,
        )
        return {"success": False, "error": "Redis unavailable"}

    # Distributed lock prevents concurrent rebuilds (e.g. duplicate job enqueue)
    lock = redis.lock(RedisKeys.REBUILD_LOCK_KEY, timeout=RedisKeys.REBUILD_LOCK_TIMEOUT)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        logger.info("Rebuild lock is busy; retrying the generation")
        raise Retry(defer=timedelta(seconds=10))

    try:
        try:
            return await _rebuild_embeddings_locked(
                vector_client,
                redis,
                config,
                expected_version=expected_version,
                expected_backend=expected_backend,
                expected_store_fingerprint=expected_store_fingerprint,
                expected_model_fingerprint=expected_model_fingerprint,
            )
        except StaleEmbeddingRebuildError as error:
            logger.info("Skipping stale embedding rebuild", extra={"error": str(error)})
            return {"success": False, "skipped": "stale rebuild generation"}
        except EmbeddingRebuildExecutionError as error:
            logger.error("Embedding rebuild failed", exc_info=True)
            await _mark_rebuild_error(
                error.original_error,
                expected_version=error.version,
                expected_rebuild_id=error.rebuild_id,
                expected_statuses={VectorizationStatus.REBUILDING.value},
            )
            return {"success": False, "error": str(error.original_error)}
        except Exception as error:
            logger.error("Embedding rebuild failed before generation start", exc_info=True)
            await _mark_rebuild_error_for_version(
                error,
                expected_version=expected_version,
            )
            return {"success": False, "error": str(error)}
    finally:
        with contextlib.suppress(Exception):
            await lock.release()


async def _rebuild_embeddings_locked(
    vector_client: Any,
    redis: Any,
    config: dict[str, Any] | None,
    *,
    expected_version: str | None,
    expected_backend: str | None,
    expected_store_fingerprint: str | None,
    expected_model_fingerprint: str | None,
) -> dict[str, Any]:
    """Inner rebuild logic — must be called with the distributed lock held."""
    async with get_session_context() as session:
        config_service = TypedConfigService(session)
        current = await config_service.get(EmbeddingConfig)
        if expected_version is not None and current.version != expected_version:
            logger.info(
                "Skipping stale rebuild request",
                extra={"expected_version": expected_version, "current_version": current.version},
            )
            return {"success": False, "skipped": "stale config version"}
        if current.status == VectorizationStatus.REBUILDING:
            return {"success": False, "skipped": "rebuild already in progress"}

        runtime_backend = vector_backend_config.backend.lower()
        runtime_store_fingerprint = vector_store_fingerprint()
        target_backend = current.target_vector_backend or expected_backend or runtime_backend
        target_store_fingerprint = (
            current.target_vector_store_fingerprint
            or expected_store_fingerprint
            or runtime_store_fingerprint
        )
        if (
            target_backend.lower() != runtime_backend
            or target_store_fingerprint != runtime_store_fingerprint
        ):
            raise StaleEmbeddingRebuildError("Rebuild target does not belong to this deployment")

        # Mark rebuild started (sets rebuild_id, rebuild_started_at, status=REBUILDING)
        rebuild_id = await config_service.start_rebuild(expected_version=current.version)
        if rebuild_id is None:
            raise StaleEmbeddingRebuildError("Config generation changed before rebuild could start")

        try:
            # Load the same typed DB configuration generation that validation used.
            if config is None:
                config = current.model_dump(mode="python")

            settings = EmbeddingSettings(
                **{k: v for k, v in config.items() if k in EmbeddingSettings.model_fields}
            )
            dimension = settings.dimension
            runtime_model_fingerprint = embedding_model_fingerprint(
                settings.provider,
                settings.model,
                settings.dimension,
                settings.base_url,
            )
            if (
                expected_model_fingerprint is not None
                and expected_model_fingerprint != runtime_model_fingerprint
            ) or (
                current.target_model_fingerprint is not None
                and current.target_model_fingerprint != runtime_model_fingerprint
            ):
                raise StaleEmbeddingRebuildError(
                    "Embedding model fingerprint changed before rebuild"
                )

            # Re-check after publishing PREPARING and before the destructive
            # boundary. A disable/cancel/backend transition invalidates this job.
            session.expire_all()
            generation = await config_service.get(EmbeddingConfig)
            if (
                generation.version != current.version
                or generation.rebuild_id != rebuild_id
                or generation.status != VectorizationStatus.REBUILDING
                or generation.rebuild_phase != EmbeddingRebuildPhase.PREPARING
            ):
                raise StaleEmbeddingRebuildError("Rebuild generation changed before recreation")

            # Recreate vector storage (drop + create) for new model
            # NOTE: Point of no return — old embeddings are gone after this.
            await vector_client.recreate_collections(
                dimension,
                settings.provider,
                settings.model,
            )
            logger.info(f"Recreated vector collections with dimension={dimension}")

            # Check again before touching relational state. The conditional
            # generation update below performs the final atomic fence.
            session.expire_all()
            generation = await config_service.get(EmbeddingConfig)
            if (
                generation.version != current.version
                or generation.rebuild_id != rebuild_id
                or generation.status != VectorizationStatus.REBUILDING
                or generation.rebuild_phase != EmbeddingRebuildPhase.PREPARING
            ):
                raise StaleEmbeddingRebuildError("Rebuild generation changed during recreation")

            # Mark all entries pending for the new model. Historical duplicate
            # (feed_id, guid) rows indicate a violated relational invariant.
            # Continuing after clearing the vector store would leave those
            # rows marked done without vectors and trigger endless rebuilds.
            try:
                await session.execute(
                    update(Entry).values(
                        embedding_status="pending",
                        embedding_error=None,
                    )
                )
            except IntegrityError as integrity_error:
                # Rollback FIRST — asyncpg rejects any SQL while a transaction is in
                # the failed state, so we must clear it before querying for duplicates.
                await session.rollback()
                duplicate_entry_ids = await _find_duplicate_entry_ids(session)
                if not duplicate_entry_ids:
                    raise

                raise RuntimeError(
                    "Embedding rebuild cannot continue: "
                    f"{len(duplicate_entry_ids)} entries violate unique (feed_id, guid); "
                    "deduplicate the relational data and retry"
                ) from integrity_error
            # Vector preference collections were recreated above. Clear the DB
            # affinity half too; only users with current durable history are
            # reconstructed in the next phase.
            await session.execute(delete(UserPreferenceStats))
            updated_generation = await config_service.update_embedding_generation(
                expected_version=current.version,
                expected_rebuild_id=rebuild_id,
                expected_statuses={VectorizationStatus.REBUILDING.value},
                vector_backend=runtime_backend,
                vector_store_fingerprint=runtime_store_fingerprint,
                model_fingerprint=runtime_model_fingerprint,
                target_vector_backend=None,
                target_vector_store_fingerprint=None,
                target_model_fingerprint=None,
                target_force_rebuild=False,
                rebuild_phase=EmbeddingRebuildPhase.EMBEDDINGS,
            )
            if updated_generation is None:
                raise StaleEmbeddingRebuildError(
                    "Rebuild generation changed before relational commit"
                )
        except StaleEmbeddingRebuildError:
            raise
        except Exception as error:
            raise EmbeddingRebuildExecutionError(
                error,
                version=current.version,
                rebuild_id=rebuild_id,
            ) from error

        # Count pending entries
        total_result = await session.execute(
            select(func.count()).select_from(Entry).where(Entry.embedding_status == "pending")
        )
        total_pending: int = total_result.scalar_one()

        # Nothing to embed (e.g. brand-new instance with no entries yet, or every
        # entry was a skipped duplicate). Move directly to preference reconstruction.
        if total_pending == 0:
            queued_preferences = await start_preference_rebuild_phase(
                session,
                redis,
                config_service,
                rebuild_id,
            )
            logger.info("Entry rebuild completed immediately: no entries to embed")
            return {
                "success": True,
                "queued_entries": 0,
                "queued_batches": 0,
                "queued_preferences": queued_preferences,
                "rebuild_id": rebuild_id,
                "dimension": dimension,
            }

        # Enqueue batch embedding jobs (much more efficient than one job per entry)
        num_batches = max(1, (total_pending + REBUILD_BATCH_SIZE - 1) // REBUILD_BATCH_SIZE)
        batch_prefix = f"rebuild_{uuid4().hex}"
        for i in range(num_batches):
            await redis.enqueue_job(
                "batch_generate_embeddings",
                REBUILD_BATCH_SIZE,
                rebuild_id,
                runtime_backend,
                runtime_store_fingerprint,
                runtime_model_fingerprint,
                _job_id=f"{batch_prefix}_{i}",
            )

        logger.info(
            "Enqueued batch embedding jobs for rebuild",
            extra={"total_pending": total_pending, "num_batches": num_batches},
        )

        # Status stays REBUILDING in the embeddings phase. Maintenance starts
        # preference jobs only after all entries become terminal.

        return {
            "success": True,
            "queued_entries": total_pending,
            "queued_batches": num_batches,
            "queued_preferences": 0,
            "rebuild_id": rebuild_id,
            "dimension": dimension,
        }


async def start_preference_rebuild_phase(
    session: AsyncSession,
    redis: Any,
    config_service: TypedConfigService,
    rebuild_id: str,
) -> int:
    """Stage and enqueue preference rebuilds for the current generation.

    The caller must hold ``RedisKeys.REBUILD_LOCK_KEY``. Phase state is saved
    before jobs are enqueued so maintenance can recover an interrupted enqueue.
    """
    current = await config_service.get(EmbeddingConfig)
    if current.status != VectorizationStatus.REBUILDING or current.rebuild_id != rebuild_id:
        return 0

    user_ids = await get_preference_history_user_ids(session)
    updated = await config_service.update_embedding_generation(
        expected_version=current.version,
        expected_rebuild_id=rebuild_id,
        expected_statuses={VectorizationStatus.REBUILDING.value},
        rebuild_phase=EmbeddingRebuildPhase.PREFERENCES,
    )
    if updated is None:
        return 0

    if not user_ids:
        await config_service.complete_rebuild(expected_rebuild_id=rebuild_id)
        logger.info(
            "Embedding rebuild completed with no preference history",
            extra={"rebuild_id": rebuild_id},
        )
        return 0

    pending_key = RedisKeys.rebuild_preferences(rebuild_id)
    await redis.sadd(pending_key, *user_ids)
    await redis.expire(pending_key, RedisKeys.REBUILD_PREFERENCES_TTL)

    for user_id in user_ids:
        await redis.enqueue_job(
            "rebuild_user_preference",
            user_id,
            rebuild_id,
            current.vector_backend,
            current.vector_store_fingerprint,
            current.model_fingerprint,
            _job_id=f"rebuild_pref_{rebuild_id}_{user_id}",
        )

    logger.info(
        "Enqueued preference rebuild phase",
        extra={"rebuild_id": rebuild_id, "users": len(user_ids)},
    )
    return len(user_ids)


async def _mark_rebuild_error(
    error: Exception,
    *,
    expected_version: str | None,
    expected_rebuild_id: str | None,
    expected_statuses: set[str],
) -> None:
    """Mark only the generation that actually experienced the failure."""
    async with get_session_context() as session:
        config_service = TypedConfigService(session)
        current = await config_service.get(EmbeddingConfig)
        await config_service.update_embedding_generation(
            expected_version=expected_version,
            expected_rebuild_id=expected_rebuild_id,
            expected_statuses=expected_statuses,
            status=VectorizationStatus.ERROR,
            last_error=f"Embedding rebuild failed: {error}",
            last_error_at=datetime.now(UTC),
            error_count=current.error_count + 1,
            target_vector_backend=None,
            target_vector_store_fingerprint=None,
            target_model_fingerprint=None,
            target_force_rebuild=False,
            rebuild_id=None,
            rebuild_started_at=None,
            rebuild_phase=None,
        )


async def _mark_rebuild_error_for_version(
    error: Exception,
    *,
    expected_version: str | None,
) -> None:
    """Resolve the matching phase/id, then conditionally mark that version."""
    async with get_session_context() as session:
        current = await TypedConfigService(session).get(EmbeddingConfig)
    if current.version != expected_version or current.status not in (
        VectorizationStatus.VALIDATING,
        VectorizationStatus.REBUILDING,
    ):
        return
    await _mark_rebuild_error(
        error,
        expected_version=expected_version,
        expected_rebuild_id=current.rebuild_id,
        expected_statuses={current.status.value},
    )
