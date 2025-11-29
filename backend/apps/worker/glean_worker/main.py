"""
Glean Worker - arq task queue entry point.

This module configures the arq worker with task functions,
cron jobs, and Redis connection settings.
"""

from arq import cron
from arq.connections import RedisSettings

from .config import settings
from .tasks import feed_fetcher


async def startup(ctx: dict) -> None:
    """
    Worker startup handler.

    Args:
        ctx: Worker context dictionary for shared resources.
    """
    print("Starting Glean Worker")
    # TODO: Initialize database connection


async def shutdown(ctx: dict) -> None:
    """
    Worker shutdown handler.

    Args:
        ctx: Worker context dictionary.
    """
    print("Shutting down Glean Worker")
    # TODO: Close database connection


class WorkerSettings:
    """
    arq Worker configuration.

    Defines task functions, cron jobs, and worker settings.
    """

    # Registered task functions
    functions = [
        feed_fetcher.fetch_feed,
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
