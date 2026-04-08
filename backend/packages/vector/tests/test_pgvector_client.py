"""Tests for PgVectorClient behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import BIGINT, Column, Float, Integer, MetaData, String, Table

from glean_vector.clients.pgvector_client import PgVectorClient


def _build_client_tables(client: PgVectorClient) -> None:
    metadata = MetaData()
    client._metadata = metadata
    client._entries_table = Table(
        "entry_embeddings",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("embedding", String),
        Column("feed_id", String(36)),
        Column("published_at", BIGINT),
        Column("language", String(10)),
        Column("word_count", Integer),
        Column("author", String(200)),
    )
    client._prefs_table = Table(
        "user_preference_vectors",
        metadata,
        Column("id", String(50), primary_key=True),
        Column("user_id", String(36)),
        Column("vector_type", String(20)),
        Column("embedding", String),
        Column("sample_count", Float),
        Column("updated_at", BIGINT),
    )
    client._meta_table = Table(
        "vector_store_metadata",
        metadata,
        Column("name", String(50), primary_key=True),
        Column("model_signature", String(255)),
        Column("updated_at", BIGINT),
    )


def test_pgvector_client_defaults_require_rebuild() -> None:
    """Compatibility checks default to rebuild-required path."""
    client = PgVectorClient()
    compatible, reason = client.check_model_compatibility(1536, "openai", "text-embedding-3-small")
    assert compatible is False
    assert reason is not None


def test_pgvector_client_collections_exist_defaults_false() -> None:
    """collections_exist returns False before backend initialization."""
    client = PgVectorClient()
    assert client.collections_exist() is False


@pytest.mark.asyncio
async def test_pgvector_client_ensure_collections_is_idempotent() -> None:
    """Repeated ensure_collections calls with the same model should not rewrite schema metadata."""
    client = PgVectorClient()
    client._connected = True
    _build_client_tables(client)

    sql_calls: list[str] = []

    class FakeConn:
        async def exec_driver_sql(self, sql: str) -> None:
            sql_calls.append(sql)

        async def run_sync(self, fn) -> None:
            return None

    class FakeBegin:
        async def __aenter__(self) -> FakeConn:
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    client._engine = SimpleNamespace(begin=lambda: FakeBegin())
    client._execute = AsyncMock()

    await client.ensure_collections(1536, "openai", "text-embedding-3-small")
    await client.ensure_collections(1536, "openai", "text-embedding-3-small")

    assert len(sql_calls) == 4
    assert client._execute.await_count == 2
