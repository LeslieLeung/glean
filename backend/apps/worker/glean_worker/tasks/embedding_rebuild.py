"""Embedding rebuild task."""

from typing import Any

from sqlalchemy import select, update

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig as EmbeddingConfigSchema
from glean_core.schemas.config import VectorizationStatus
from glean_core.services import TypedConfigService
from glean_core.services.system_config_service import SystemConfigService
from glean_database.models import Entry, UserPreferenceStats
from glean_database.session import get_session
from glean_vector.clients.milvus_client import MilvusClient
from glean_vector.config import EmbeddingConfig as EmbeddingSettings
from glean_vector.config import embedding_config as env_embedding_config

logger = get_logger(__name__)


async def rebuild_embeddings(ctx: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Rebuild embeddings after config change.

    Steps:
      1) Load embedding config (payload passed or system config / env fallback)
      2) Update status to REBUILDING
      3) Recreate Milvus collections if dimension changed
      4) Mark all entries pending
      5) Enqueue embedding jobs in batches
      6) Enqueue user preference rebuild jobs
      7) Keep status as REBUILDING (will be set to IDLE when all done)
    """
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"success": False, "error": "Milvus unavailable"}

    redis = ctx.get("redis")
    if not redis:
        return {"success": False, "error": "Redis unavailable"}

    async for session in get_session():
        # Update status to REBUILDING so embedding tasks can proceed
        config_service = TypedConfigService(session)
        await config_service.update(
            EmbeddingConfigSchema,
            status=VectorizationStatus.REBUILDING,
        )
        # Load config
        if config is None:
            scs = SystemConfigService(session)
            config = await scs.get_config("embedding.config")

        if not config:
            # Fallback to env defaults
            env_conf = env_embedding_config.model_dump()
            config = {
                "provider": env_conf["provider"],
                "model": env_conf["model"],
                "dimension": env_conf["dimension"],
                "api_key": env_conf.get("api_key") or "",
                "base_url": env_conf.get("base_url"),
                "rate_limit": {"default": 10, "providers": {}},
            }

        settings = EmbeddingSettings(**{k: v for k, v in config.items() if k in EmbeddingSettings.model_fields})
        dimension = settings.dimension

        # Recreate Milvus collections (drop + create) for new model
        # This also drops user_preferences collection, so we need to rebuild them
        milvus_client.recreate_collections(dimension, settings.provider, settings.model)
        logger.info(f"Recreated Milvus collections with dimension={dimension}")

        # Mark all entries pending for new model
        await session.execute(
            update(Entry).values(
                embedding_status="pending",
                embedding_error=None,
            )
        )
        await session.commit()

        # Enqueue embedding jobs in batches
        total_result = await session.execute(select(Entry.id))
        entry_ids = [row[0] for row in total_result.all()]

        for entry_id in entry_ids:
            await redis.enqueue_job("generate_entry_embedding", entry_id)

        logger.info(f"Enqueued {len(entry_ids)} embedding jobs")

        # Enqueue user preference rebuild jobs for all users with preference data
        # User preference vectors were deleted when collections were recreated,
        # so we need to rebuild them from historical feedback
        users_result = await session.execute(
            select(UserPreferenceStats.user_id).distinct()
        )
        user_ids = [row[0] for row in users_result.all()]

        for user_id in user_ids:
            await redis.enqueue_job("rebuild_user_preference", user_id=user_id)

        logger.info(f"Enqueued {len(user_ids)} preference rebuild jobs")

        # Keep status as REBUILDING - the status API will automatically
        # update to IDLE when all pending entries are processed
        # Note: We don't set to IDLE here because tasks are still in queue

        return {
            "success": True,
            "queued_entries": len(entry_ids),
            "queued_preferences": len(user_ids),
            "dimension": dimension,
        }

    return {"success": False, "error": "No database session"}

