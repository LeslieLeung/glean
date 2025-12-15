"""Configuration for vector services."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Find .env file in project root
_env_file = Path(__file__).parent.parent.parent.parent.parent / ".env"


class EmbeddingConfig(BaseSettings):
    """Embedding service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "openai"
    api_key: str = ""
    model: str = "text-embedding-3-small"
    dimension: int = 1536
    batch_size: int = 20
    max_retries: int = 3
    timeout: int = 30
    base_url: str | None = None
    rate_limit_default: int = 10  # rpm
    rate_limit_providers: dict[str, int] = {}


class MilvusConfig(BaseSettings):
    """Milvus configuration."""

    model_config = SettingsConfigDict(
        env_prefix="MILVUS_",
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "localhost"
    port: int = 19530
    user: str = ""
    password: str = ""
    entries_collection: str = "entries"
    prefs_collection: str = "user_preferences"


class PreferenceConfig(BaseSettings):
    """Preference calculation configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PREFERENCE_",
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_score: float = 50.0
    confidence_threshold: int = 10
    like_weight: float = 1.0
    bookmark_weight: float = 0.7
    source_boost_max: float = 5.0
    author_boost_max: float = 3.0


class ScoreConfig(BaseSettings):
    """Score calculation configuration."""

    model_config = SettingsConfigDict(
        env_prefix="SCORE_",
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    recommend_threshold: float = 70.0
    low_interest_threshold: float = 40.0
    cache_ttl: int = 3600


# Global config instances
embedding_config = EmbeddingConfig()
milvus_config = MilvusConfig()
preference_config = PreferenceConfig()
score_config = ScoreConfig()


def embedding_config_from_settings(data: dict) -> EmbeddingConfig:
    """
    Build EmbeddingConfig from stored settings dict (system_settings).

    Expected keys: provider, model, dimension, api_key, base_url, rate_limit {default, providers},
    timeout, batch_size, max_retries.
    """
    rate_limit = data.get("rate_limit") or {}
    return EmbeddingConfig(
        provider=data.get("provider", embedding_config.provider),
        model=data.get("model", embedding_config.model),
        dimension=data.get("dimension", embedding_config.dimension),
        api_key=data.get("api_key", embedding_config.api_key),
        base_url=data.get("base_url", embedding_config.base_url),
        timeout=data.get("timeout", embedding_config.timeout),
        batch_size=data.get("batch_size", embedding_config.batch_size),
        max_retries=data.get("max_retries", embedding_config.max_retries),
        rate_limit_default=rate_limit.get("default", embedding_config.rate_limit_default),
        rate_limit_providers=rate_limit.get("providers", embedding_config.rate_limit_providers),
    )
