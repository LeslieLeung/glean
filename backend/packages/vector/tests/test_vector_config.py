"""Tests for vector configuration validation."""

import pytest
from pydantic import ValidationError

from glean_vector.config import (
    VectorBackendConfig,
    is_active_vector_backend,
    vector_backend_config,
    vector_store_fingerprint,
)


def test_vector_backend_config_normalizes_backend() -> None:
    """Should accept uppercase env-style values and normalize them."""
    config = VectorBackendConfig(backend="PGVECTOR")
    assert config.backend == "pgvector"


def test_vector_backend_config_rejects_unknown_backend() -> None:
    """Should fail fast on unsupported vector backends."""
    with pytest.raises(ValidationError, match="VECTOR_BACKEND must be either"):
        VectorBackendConfig(backend="clickhouse")


def test_active_backend_requires_explicit_pgvector_adoption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vector_backend_config, "backend", "pgvector")

    assert is_active_vector_backend(None) is False
    assert is_active_vector_backend("milvus") is False
    assert is_active_vector_backend("PGVECTOR") is False
    assert is_active_vector_backend("PGVECTOR", vector_store_fingerprint()) is True


def test_active_backend_requires_legacy_milvus_adoption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vector_backend_config, "backend", "milvus")

    assert is_active_vector_backend(None) is False
    assert is_active_vector_backend("milvus") is False
    assert is_active_vector_backend("milvus", vector_store_fingerprint()) is True
    assert is_active_vector_backend("pgvector") is False
