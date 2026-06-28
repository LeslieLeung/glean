"""Embedding rebuild task."""

import contextlib
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.redis_keys import RedisKeys
from glean_core.services import TypedConfigService
from glean_core.services.system_config_service import SystemConfigService
from glean_database.models import Entry, UserPreferenceStats
from glean_database.session import get_session_context
from glean_vector.config import EmbeddingConfig as EmbeddingSettings
from glean_vector.config import embedding_config as env_embedding_config

from ._vector_client import ensure_vector_client

logger = get_logger(__name__)

REBUILD_BATCH_SIZE = 200


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
    ctx: dict[str, Any], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Rebuild embeddings after config change.

    Steps:
      1) Load embedding config (payload passed or system config / env fallback)
      2) Update status to REBUILDING
      3) Recreate vector collections if dimension changed
      4) Mark all entries pending
      5) Enqueue embedding jobs in batches
      6) Enqueue user preference rebuild jobs
      7) Keep status as REBUILDING (will be set to IDLE when all done)
    """
    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        if vector_error:
            return {"success": False, "error": f"Vector backend unavailable: {vector_error}"}
        return {"success": False, "error": "Vector backend unavailable"}

    redis = ctx.get("redis")
    if not redis:
        return {"success": False, "error": "Redis unavailable"}

    # Distributed lock prevents concurrent rebuilds (e.g. duplicate job enqueue)
    lock = redis.lock(RedisKeys.REBUILD_LOCK_KEY, timeout=RedisKeys.REBUILD_LOCK_TIMEOUT)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        logger.warning("Rebuild already in progress (lock held), skipping")
        return {"success": False, "error": "Rebuild already in progress"}

    try:
        return await _rebuild_embeddings_locked(vector_client, redis, config)
    finally:
        with contextlib.suppress(Exception):
            await lock.release()


async def _rebuild_embeddings_locked(
    vector_client: Any,
    redis: Any,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Inner rebuild logic — must be called with the distributed lock held."""
    async with get_session_context() as session:
        # Mark rebuild started (sets rebuild_id, rebuild_started_at, status=REBUILDING)
        config_service = TypedConfigService(session)
        await config_service.start_rebuild()
        # Commit status change BEFORE modifying vector data to prevent inconsistent state
        await session.commit()

        # Load config
        if config is None:
            scs = SystemConfigService(session)
            config = await scs.get_config("embedding.config")

        if not config:
            env_conf = env_embedding_config.model_dump()
            config = {
                "provider": env_conf["provider"],
                "model": env_conf["model"],
                "dimension": env_conf["dimension"],
                "api_key": env_conf.get("api_key") or "",
                "base_url": env_conf.get("base_url"),
                "rate_limit": {"default": 10, "providers": {}},
            }

        settings = EmbeddingSettings(
            **{k: v for k, v in config.items() if k in EmbeddingSettings.model_fields}
        )
        dimension = settings.dimension

        # Recreate vector storage (drop + create) for new model
        # NOTE: Point of no return — old embeddings are gone after this.
        await vector_client.recreate_collections(dimension, settings.provider, settings.model)
        logger.info(f"Recreated vector collections with dimension={dimension}")

        # Mark all entries pending for new model
        # If historical duplicate (feed_id, guid) rows exist, a full-table update can
        # trigger uq_feed_guid conflicts. We skip those rows as a safe fallback.
        duplicate_entry_ids: list[str] = []
        try:
            await session.execute(
                update(Entry).values(
                    embedding_status="pending",
                    embedding_error=None,
                )
            )
        except IntegrityError:
            # Rollback FIRST — asyncpg rejects any SQL while a transaction is in
            # the failed state, so we must clear it before querying for duplicates.
            await session.rollback()
            duplicate_entry_ids = await _find_duplicate_entry_ids(session)
            if not duplicate_entry_ids:
                raise

            logger.warning(
                "Detected duplicate (feed_id, guid) entries during rebuild; "
                "skipping them for this run",
                extra={"duplicate_entry_count": len(duplicate_entry_ids)},
            )
            await session.execute(
                update(Entry)
                .where(Entry.id.not_in(duplicate_entry_ids))
                .values(
                    embedding_status="pending",
                    embedding_error=None,
                )
            )
        await session.commit()

        # Count pending entries
        total_result = await session.execute(
            select(func.count()).select_from(Entry).where(Entry.embedding_status == "pending")
        )
        total_pending: int = total_result.scalar_one()

        # Nothing to embed (e.g. brand-new instance with no entries yet, or every
        # entry was a skipped duplicate).  Complete the rebuild immediately so the
        # status does not stay stuck in REBUILDING forever — the auto-complete
        # checks elsewhere require at least one terminal entry to fire.
        if total_pending == 0:
            await config_service.complete_rebuild()
            await session.commit()
            logger.info("Rebuild completed immediately: no entries to embed")
            return {
                "success": True,
                "queued_entries": 0,
                "queued_batches": 0,
                "queued_preferences": 0,
                "dimension": dimension,
                "skipped_duplicate_entries": len(duplicate_entry_ids),
            }

        # Enqueue batch embedding jobs (much more efficient than one job per entry)
        num_batches = max(1, (total_pending + REBUILD_BATCH_SIZE - 1) // REBUILD_BATCH_SIZE)
        batch_prefix = f"rebuild_{uuid4().hex}"
        for i in range(num_batches):
            await redis.enqueue_job(
                "batch_generate_embeddings",
                REBUILD_BATCH_SIZE,
                _job_id=f"{batch_prefix}_{i}",
            )

        logger.info(
            "Enqueued batch embedding jobs for rebuild",
            extra={"total_pending": total_pending, "num_batches": num_batches},
        )

        # Enqueue user preference rebuild jobs
        users_result = await session.execute(select(UserPreferenceStats.user_id).distinct())
        user_ids = [row[0] for row in users_result.all()]

        for user_id in user_ids:
            await redis.enqueue_job("rebuild_user_preference", user_id=user_id)

        logger.info(f"Enqueued {len(user_ids)} preference rebuild jobs")

        # Status stays REBUILDING — the maintenance cron will transition
        # to IDLE when all entries reach a terminal state.

        return {
            "success": True,
            "queued_entries": total_pending,
            "queued_batches": num_batches,
            "queued_preferences": len(user_ids),
            "dimension": dimension,
            "skipped_duplicate_entries": len(duplicate_entry_ids),
        }
