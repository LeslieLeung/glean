"""
Glean Worker - arq task queue entry point.

This module configures the arq worker with task functions,
cron jobs, and Redis connection settings.
"""

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from glean_core import init_logging, get_logger
from glean_database.session import init_database
from glean_vector.clients.milvus_client import MilvusClient

from .config import settings
from .tasks import (
    bookmark_metadata,
    cleanup,
    embedding_rebuild,
    embedding_worker,
    feed_fetcher,
    preference_worker,
    subscription_cleanup,
)

# Initialize logging system
init_logging()

# Get logger instance
logger = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """
    Worker startup handler.

    Args:
        ctx: Worker context dictionary for shared resources.
    """
    logger.info("=" * 60)
    logger.info("Starting Glean Worker")
    logger.info(
        f"Database URL: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'configured'}"
    )
    logger.info(
        f"Redis URL: {settings.redis_url.split('@')[1] if '@' in settings.redis_url else 'configured'}"
    )
    init_database(settings.database_url)
    logger.info("Database initialized")

    # Initialize Milvus client (M3)
    milvus_client = MilvusClient()
    try:
        milvus_client.connect()
        ctx["milvus_client"] = milvus_client
        logger.info("Milvus client initialized")
    except Exception as e:
        logger.warning(f"Failed to connect to Milvus: {e}")
        logger.info("Embedding and preference tasks will be disabled")
        ctx["milvus_client"] = None

    # Dynamically log registered task functions
    logger.info("Registered task functions:")
    for func in WorkerSettings.functions:
        logger.info(f"  - {func.__name__}")

    # Dynamically log scheduled cron jobs
    logger.info("Scheduled cron jobs:")
    for job in WorkerSettings.cron_jobs:
        # Extract function name and cron schedule from job
        func_name = job.func.__name__ if hasattr(job, "func") else "unknown"
        minute = getattr(job, "minute", "unknown")
        logger.info(f"  - {func_name} (minute: {minute})")
    logger.info("=" * 60)


async def shutdown(ctx: dict[str, Any]) -> None:
    """
    Worker shutdown handler.

    Args:
        ctx: Worker context dictionary.
    """
    logger.info("=" * 60)
    logger.info("Shutting down Glean Worker")

    # Disconnect Milvus client
    milvus_client = ctx.get("milvus_client")
    if milvus_client:
        milvus_client.disconnect()
        logger.info("Milvus client disconnected")

    logger.info("=" * 60)


class WorkerSettings:
    """
    arq Worker configuration.

    Defines task functions, cron jobs, and worker settings.
    """

    # Registered task functions
    functions = [
        feed_fetcher.fetch_feed_task,
        feed_fetcher.fetch_all_feeds,
        cleanup.cleanup_read_later,
        bookmark_metadata.fetch_bookmark_metadata_task,
        # M3: Embedding tasks (triggered immediately after feed fetch)
        embedding_worker.generate_entry_embedding,
        embedding_worker.batch_generate_embeddings,
        embedding_worker.retry_failed_embeddings,
        embedding_worker.validate_and_rebuild_embeddings,
        embedding_rebuild.rebuild_embeddings,
        # M3: Preference tasks
        preference_worker.update_user_preference,
        preference_worker.rebuild_user_preference,
        # Subscription cleanup
        subscription_cleanup.cleanup_orphan_embeddings,
    ]

    # Scheduled cron jobs
    cron_jobs = [
        # Feed fetch (every 15 minutes)
        cron(feed_fetcher.scheduled_fetch, minute={0, 15, 30, 45}),
        # Read-later cleanup (hourly at minute 0)
        cron(cleanup.scheduled_cleanup, minute=0),
    ]

    # Lifecycle handlers
    on_startup = startup
    on_shutdown = shutdown

    # Redis connection settings
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # Worker settings
    max_jobs = 20
    job_timeout = 300
    keep_result = 3600
