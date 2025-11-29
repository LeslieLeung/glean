"""
Application configuration management.

This module defines the application settings using Pydantic BaseSettings
for automatic environment variable loading and validation.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration settings.

    All settings can be overridden via environment variables.

    Attributes:
        version: Application version string.
        debug: Enable debug mode.
        secret_key: Secret key for JWT signing.
        database_url: PostgreSQL connection URL.
        redis_url: Redis connection URL.
        jwt_algorithm: Algorithm for JWT encoding.
        jwt_access_token_expire_minutes: Access token expiration time.
        jwt_refresh_token_expire_days: Refresh token expiration time.
        cors_origins: List of allowed CORS origins.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Database settings
    database_url: str = "postgresql+asyncpg://glean:changeme@localhost:5432/glean"

    # Redis settings
    redis_url: str = "redis://localhost:6379/0"

    # JWT settings
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # CORS settings
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Returns:
        Singleton Settings instance.
    """
    return Settings()


settings = get_settings()
