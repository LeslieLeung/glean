"""
Application configuration management.

This module defines the application settings using Pydantic BaseSettings
for automatic environment variable loading and validation.
"""

from functools import lru_cache

from pydantic import Field
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
        mcp_issuer_url: MCP server issuer URL for authentication.
        mcp_resource_server_url: MCP server resource server URL.
    """

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    # Version is injected via APP_VERSION env variable during Docker build
    # or defaults to "dev" for local development
    version: str = Field(default="dev", validation_alias="APP_VERSION")
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

    # MCP Server settings
    mcp_issuer_url: str = "http://localhost:8000"
    mcp_resource_server_url: str = "http://localhost:8000/mcp"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Returns:
        Singleton Settings instance.
    """
    return Settings()


settings = get_settings()
