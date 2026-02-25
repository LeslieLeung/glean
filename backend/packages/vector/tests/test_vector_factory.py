"""Tests for vector backend client factory."""

import pytest

from glean_vector.clients import MilvusClient, PgVectorClient, create_vector_store_client
from glean_vector.config import vector_backend_config


def test_create_vector_store_client_milvus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory returns MilvusClient when backend is milvus."""
    monkeypatch.setattr(vector_backend_config, "backend", "milvus")
    client = create_vector_store_client()
    assert isinstance(client, MilvusClient)


def test_create_vector_store_client_pgvector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory returns PgVectorClient when backend is pgvector."""
    monkeypatch.setattr(vector_backend_config, "backend", "pgvector")
    client = create_vector_store_client()
    assert isinstance(client, PgVectorClient)


def test_create_vector_store_client_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory raises on unsupported backend."""
    monkeypatch.setattr(vector_backend_config, "backend", "unknown")
    with pytest.raises(ValueError, match="Unsupported vector backend"):
        create_vector_store_client()
