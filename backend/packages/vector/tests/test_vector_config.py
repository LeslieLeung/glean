"""Tests for vector configuration validation."""

import pytest
from pydantic import ValidationError

from glean_vector.config import VectorBackendConfig


def test_vector_backend_config_normalizes_backend() -> None:
    """Should accept uppercase env-style values and normalize them."""
    config = VectorBackendConfig(backend="PGVECTOR")
    assert config.backend == "pgvector"


def test_vector_backend_config_rejects_unknown_backend() -> None:
    """Should fail fast on unsupported vector backends."""
    with pytest.raises(ValidationError, match="VECTOR_BACKEND must be either"):
        VectorBackendConfig(backend="clickhouse")
