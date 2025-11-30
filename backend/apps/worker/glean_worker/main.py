"""
Glean Worker - arq task queue entry point.

This module configures the arq worker with task functions,
cron jobs, and Redis connection settings.
"""

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from glean_database.session import init_database

from .config import settings
from .tasks import feed_fetcher


async def startup(ctx: dict[str, Any]) -> None:
    """
    Worker startup handler.

    Args:
        ctx: Worker context dictionary for shared resources.
    """
    print("=" * 60)
    print("Starting Glean Worker")
    print(
        f"Database URL: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'configured'}"
    )
    print(
        f"Redis URL: {settings.redis_url.split('@')[1] if '@' in settings.redis_url else 'configured'}"
    )
    init_database(settings.database_url)
    print("Database initialized")
    print("Registered task functions:")
    print("  - fetch_feed_task")
    print("  - fetch_all_feeds")
    print("Scheduled cron jobs:")
    print("  - scheduled_fetch (every 15 minutes: 0, 15, 30, 45)")
    print("=" * 60)


async def shutdown(ctx: dict[str, Any]) -> None:
    """
    Worker shutdown handler.

    Args:
        ctx: Worker context dictionary.
    """
    print("=" * 60)
    print("Shutting down Glean Worker")
    print("=" * 60)


class WorkerSettings:
    """
    arq Worker configuration.

    Defines task functions, cron jobs, and worker settings.
    """

    # Registered task functions
    functions = [
        feed_fetcher.fetch_feed_task,
        feed_fetcher.fetch_all_feeds,
    ]

    # Scheduled cron jobs (runs every 15 minutes)
    cron_jobs = [
        cron(feed_fetcher.scheduled_fetch, minute={0, 15, 30, 45}),
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
