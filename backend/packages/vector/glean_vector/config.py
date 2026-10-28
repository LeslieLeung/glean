"""Configuration for vector services."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

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


class VectorBackendConfig(BaseSettings):
    """Vector backend selector configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VECTOR_",
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend: Literal["milvus", "pgvector"] = "milvus"

    @field_validator("backend", mode="before")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        backend = str(value).lower()
        if backend not in {"milvus", "pgvector"}:
            raise ValueError("VECTOR_BACKEND must be either 'milvus' or 'pgvector'")
        return backend


class PgVectorConfig(BaseSettings):
    """pgvector backend configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PGVECTOR_",
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = ""
    entries_table: str = "entry_embeddings"
    prefs_table: str = "user_preference_vectors"
    metadata_table: str = "vector_store_metadata"


class DatabaseURLConfig(BaseSettings):
    """Shared relational URL fallback loaded from the repository .env."""

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://glean:changeme@localhost:5432/glean"


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
vector_backend_config = VectorBackendConfig()
pgvector_config = PgVectorConfig()
database_url_config = DatabaseURLConfig()
preference_config = PreferenceConfig()
score_config = ScoreConfig()


def embedding_model_fingerprint(
    provider: str,
    model: str,
    dimension: int,
    base_url: str | None,
) -> str:
    """Return a stable identity for the embedding vector space."""
    payload = {
        "provider": provider.strip().lower(),
        "model": model.strip(),
        "dimension": dimension,
        "base_url": (base_url or "").strip().rstrip("/"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def vector_store_fingerprint() -> str:
    """Return a non-secret fingerprint of the selected store location."""
    backend = vector_backend_config.backend.lower()
    if backend == "milvus":
        payload: dict[str, Any] = {
            "backend": backend,
            "host": milvus_config.host.strip().lower(),
            "port": milvus_config.port,
            "entries": milvus_config.entries_collection,
            "preferences": milvus_config.prefs_collection,
        }
    else:
        # Hashing the URL keeps credentials out of system config and API
        # responses while still detecting a deployment pointed at another DB.
        database_url = resolve_pgvector_database_url()
        try:
            database_location = make_url(database_url).render_as_string(hide_password=True)
        except Exception:
            database_location = database_url
        payload = {
            "backend": backend,
            "database_url_hash": hashlib.sha256(database_location.encode()).hexdigest(),
            "entries": pgvector_config.entries_table,
            "preferences": pgvector_config.prefs_table,
            "metadata": pgvector_config.metadata_table,
        }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def resolve_pgvector_database_url() -> str:
    """Resolve pgvector's URL using the same .env fallback as API/worker."""
    return (
        pgvector_config.database_url
        or os.getenv("DATABASE_URL", "")
        or database_url_config.database_url
    )


def is_active_vector_backend(
    stored_backend: str | None,
    stored_store_fingerprint: str | None = None,
) -> bool:
    """Return whether persisted vector data belongs to this deployment.

    Missing identity markers are deliberately *not* accepted by normal
    readers/writers. API startup performs read-only validation and adopts
    compatible legacy Milvus stores (or empty pgvector stores) first. This
    keeps a worker that starts earlier during a rolling deployment from
    provisioning or writing an unverified vector store.
    """
    runtime_backend = vector_backend_config.backend.lower()
    return (
        stored_backend is not None
        and stored_store_fingerprint is not None
        and stored_backend.lower() == runtime_backend
        and stored_store_fingerprint == vector_store_fingerprint()
    )


def is_active_embedding_model(
    stored_fingerprint: str | None,
    *,
    provider: str,
    model: str,
    dimension: int,
    base_url: str | None,
) -> bool:
    """Require the persisted generation to match this embedding vector space."""
    return stored_fingerprint is not None and stored_fingerprint == embedding_model_fingerprint(
        provider,
        model,
        dimension,
        base_url,
    )


def embedding_config_from_settings(data: dict[str, Any]) -> EmbeddingConfig:
    """
    Build EmbeddingConfig from stored settings dict (system_settings).

    Expected keys: provider, model, dimension, api_key, base_url, rate_limit {default, providers},
    timeout, batch_size, max_retries.
    """
    rate_limit: dict[str, Any] = data.get("rate_limit") or {}
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
