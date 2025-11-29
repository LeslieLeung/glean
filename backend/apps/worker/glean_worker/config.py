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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://glean:changeme@localhost:5432/glean"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached worker settings.

    Returns:
        Singleton Settings instance.
    """
    return Settings()


settings = get_settings()
