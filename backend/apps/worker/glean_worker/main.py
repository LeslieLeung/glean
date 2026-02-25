"""
Glean Worker - arq task queue entry point.

This module configures the arq worker with task functions,
cron jobs, and Redis connection settings.
"""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob

from glean_core import get_logger, init_logging
from glean_database.session import init_database
from glean_vector.clients.vector_store import create_vector_store_client
from glean_vector.config import vector_backend_config

from .config import settings
from .tasks import (
    bookmark_metadata,
    cleanup,
    embedding_maintenance,
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

TaskFunction = Callable[..., Awaitable[Any]]


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

    # Store Redis client for distributed locks (arq provides it via ctx['redis'])
    # The redis client is automatically available in the worker context
    logger.info("Redis client available for distributed locks")

    # Initialize vector backend client (M3) - optional for embedding/preference features
    try:
        vector_client = create_vector_store_client()
        vector_client.connect()
        ctx["vector_client"] = vector_client
        ctx["vector_client_error"] = None
        logger.info(
            "✓ Vector client connected successfully",
            extra={"backend": vector_backend_config.backend},
        )
    except Exception as e:
        logger.warning(
            "✗ Failed to connect to vector backend",
            extra={"backend": vector_backend_config.backend, "error": str(e)},
        )
        logger.info(
            "Worker will continue without vector backend - embedding and preference tasks "
            "will be skipped"
        )
        ctx["vector_client"] = None
        ctx["vector_client_error"] = str(e)

    # Dynamically log registered task functions
    logger.info("Registered task functions:")
    for func in WorkerSettings.functions:
        func_name = cast(str, getattr(func, "__name__", repr(func)))
        logger.info(f"  - {func_name}")

    # Dynamically log scheduled cron jobs
    logger.info("Scheduled cron jobs:")
    for job in WorkerSettings.cron_jobs:
        # Extract function name and cron schedule from job
        func_name = "unknown"
        if hasattr(job, "coroutine") and hasattr(job.coroutine, "__name__"):
            func_name = job.coroutine.__name__  # type: ignore[union-attr]
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

    # Disconnect vector client
    vector_client = ctx.get("vector_client")
    if vector_client:
        vector_client.disconnect()
        logger.info("Vector client disconnected", extra={"backend": vector_backend_config.backend})

    logger.info("=" * 60)


def get_oss_functions() -> list[TaskFunction]:
    """Return all OSS task functions."""
    return [
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
        # Embedding maintenance
        embedding_maintenance.scheduled_embedding_maintenance,
    ]


def get_oss_cron_jobs() -> list[CronJob]:
    """Return all OSS cron jobs."""
    return [
        # Feed fetch (every 15 minutes)
        cron(feed_fetcher.scheduled_fetch, minute={0, 15, 30, 45}),
        # Read-later cleanup (hourly at minute 0)
        cron(cleanup.scheduled_cleanup, minute=0),
        # Embedding maintenance: recover stuck entries + auto-complete rebuild (every 5 min)
        cron(
            embedding_maintenance.scheduled_embedding_maintenance,
            minute={3, 8, 13, 18, 23, 28, 33, 38, 43, 48, 53, 58},
        ),
    ]


class WorkerSettings:
    """
    arq Worker configuration.

    Defines task functions, cron jobs, and worker settings.
    """

    functions: list[TaskFunction] = get_oss_functions()
    cron_jobs: list[CronJob] = get_oss_cron_jobs()

    # Lifecycle handlers
    on_startup = startup
    on_shutdown = shutdown

    # Redis connection settings
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # Worker settings
    max_jobs = 20
    job_timeout = 300
    keep_result = 3600
