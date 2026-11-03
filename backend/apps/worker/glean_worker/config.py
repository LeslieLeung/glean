"""
Worker configuration management.

This module defines configuration settings for the background worker.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Worker configuration settings.

    Attributes:
        database_url: PostgreSQL connection URL.
        redis_url: Redis connection URL for task queue.
    """

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://glean:changeme@localhost:5432/glean"
    redis_url: str = "redis://localhost:6379/0"


# arq worker process settings. Embedding jobs size their claims against these.
WORKER_MAX_JOBS = 20
WORKER_JOB_TIMEOUT_SECONDS = 300
WORKER_KEEP_RESULT_SECONDS = 3600
# Leave headroom so a job can restore in-flight claims before arq cancels it.
EMBEDDING_JOB_DEADLINE_MARGIN_SECONDS = 60
# Hard cap on entries one embedding job will attempt, even at high RPM.
MAX_EMBEDDING_JOB_ENTRIES = 200


@lru_cache
def get_settings() -> Settings:
    """
    Get cached worker settings.

    Returns:
        Singleton Settings instance.
    """
    return Settings()


settings = get_settings()
