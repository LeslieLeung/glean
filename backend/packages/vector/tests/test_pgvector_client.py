"""Tests for PgVectorClient schema, model fencing, and dimension safety."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import BIGINT, Column, Float, Integer, MetaData, String, Table

from glean_vector.clients.pgvector_client import (
    PgVectorClient,
    PgVectorDimensionError,
    PgVectorModelMismatchError,
)


class FakeResult:
    def __init__(self, *, rows: list[tuple[Any, ...]] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[tuple[Any, ...]]:
        return self._rows

    def scalar_one(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class FakeConnection:
    def __init__(
        self,
        *,
        signatures: dict[str, str] | None = None,
        data_exists: bool = False,
        invalid_dimensions: int = 0,
        parent_entries_exists: bool = False,
        fail_hnsw: bool = False,
    ) -> None:
        self.signatures = signatures or {}
        self.data_exists = data_exists
        self.invalid_dimensions = invalid_dimensions
        self.parent_entries_exists = parent_entries_exists
        self.fail_hnsw = fail_hnsw
        self.sql_calls: list[str] = []
        self.statements: list[Any] = []
        self.run_sync_calls = 0

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        del params
        rendered = str(statement)
        self.statements.append(statement)
        if "vector_store_metadata" in rendered and rendered.lstrip().startswith("SELECT"):
            return FakeResult(rows=list(self.signatures.items()))
        if "to_regclass('entries')" in rendered and "pg_constraint" not in rendered:
            return FakeResult(scalar="entries" if self.parent_entries_exists else None)
        if "pg_constraint" in rendered:
            return FakeResult(scalar=None)
        return FakeResult()

    async def exec_driver_sql(self, sql: str) -> FakeResult:
        self.sql_calls.append(sql)
        if "EXISTS (SELECT 1 FROM" in sql:
            return FakeResult(scalar=self.data_exists)
        if "vector_dims(embedding) IS DISTINCT FROM" in sql:
            return FakeResult(scalar=self.invalid_dimensions)
        if sql.startswith("CREATE INDEX") and self.fail_hnsw:
            raise RuntimeError("index creation failed")
        return FakeResult()

    async def run_sync(self, fn: Any) -> None:
        del fn
        self.run_sync_calls += 1


class FakeBegin:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeSession(FakeConnection):
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def begin(self) -> FakeBegin:
        return FakeBegin(self)


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


def _prepared_client(connection: FakeConnection, *, schema_ensured: bool = False) -> PgVectorClient:
    client = PgVectorClient()
    client._connected = True
    client._schema_ensured = schema_ensured
    _build_client_tables(client)
    client._engine = SimpleNamespace(begin=lambda: FakeBegin(connection))
    client._session_maker = lambda: FakeSession(
        signatures=(
            {
                "entries": client._last_model_signature,
                "preferences": client._last_model_signature,
            }
            if client._last_model_signature is not None
            else connection.signatures
        )
    )
    return client


def test_pgvector_client_defaults_require_rebuild() -> None:
    client = PgVectorClient()
    compatible, reason = client.check_model_compatibility(1536, "openai", "text-embedding-3-small")
    assert compatible is False
    assert reason is not None
    assert client.collections_exist() is False


@pytest.mark.asyncio
async def test_disconnect_invalidates_schema_and_model_caches() -> None:
    client = PgVectorClient()
    client._connected = True
    client._schema_ensured = True
    client._last_model_signature = "openai:model:3"
    client._active_dimension = 3

    # Use a tiny async dispose stub without creating a real engine.
    async def dispose() -> None:
        return None

    client._engine = SimpleNamespace(dispose=dispose)
    await client.disconnect()

    assert client.collections_exist() is False
    assert client._last_model_signature is None
    assert client._active_dimension is None


def test_runtime_metadata_has_no_unresolved_entries_foreign_key() -> None:
    """The runtime fallback can sort/create its standalone metadata."""
    client = PgVectorClient()
    client._init_tables()

    assert [table.name for table in client._metadata.sorted_tables] == [
        "entry_embeddings",
        "user_preference_vectors",
        "vector_store_metadata",
    ]


@pytest.mark.asyncio
async def test_ensure_collections_initializes_empty_store_once() -> None:
    connection = FakeConnection()
    client = _prepared_client(connection)

    await client.ensure_collections(1536, "openai", "text-embedding-3-small")
    await client.ensure_collections(1536, "openai", "text-embedding-3-small")

    assert connection.run_sync_calls == 1
    assert connection.sql_calls.count("CREATE EXTENSION IF NOT EXISTS vector") == 1
    assert sum(sql.startswith("CREATE INDEX") for sql in connection.sql_calls) == 1
    assert (
        sum("INSERT INTO vector_store_metadata" in str(stmt) for stmt in connection.statements) == 2
    )
    assert client.check_model_compatibility(1536, "openai", "text-embedding-3-small") == (
        True,
        None,
    )


@pytest.mark.asyncio
async def test_runtime_schema_adds_fk_only_when_entries_table_is_local() -> None:
    local_connection = FakeConnection(parent_entries_exists=True)
    local_client = _prepared_client(local_connection)
    await local_client.ensure_collections(3)

    assert any(sql.startswith("ALTER TABLE") for sql in local_connection.sql_calls)

    dedicated_connection = FakeConnection(parent_entries_exists=False)
    dedicated_client = _prepared_client(dedicated_connection)
    await dedicated_client.ensure_collections(3)

    assert not any(sql.startswith("ALTER TABLE") for sql in dedicated_connection.sql_calls)


@pytest.mark.asyncio
async def test_ensure_collections_rejects_existing_model_mismatch() -> None:
    connection = FakeConnection(
        signatures={
            "entries": "openai:old-model:1536",
            "preferences": "openai:old-model:1536",
        },
        data_exists=True,
    )
    client = _prepared_client(connection, schema_ensured=True)

    with pytest.raises(PgVectorModelMismatchError, match="run a full rebuild"):
        await client.ensure_collections(1536, "openai", "new-model")


@pytest.mark.asyncio
async def test_ensure_collections_does_not_claim_unsigned_existing_data() -> None:
    connection = FakeConnection(data_exists=True)
    client = _prepared_client(connection, schema_ensured=True)

    with pytest.raises(PgVectorModelMismatchError, match="current=None"):
        await client.ensure_collections(1536, "openai", "model")

    assert not any("INSERT INTO vector_store_metadata" in str(s) for s in connection.statements)


@pytest.mark.asyncio
async def test_ensure_collections_rejects_persisted_mixed_dimensions() -> None:
    signature = "openai:model:3"
    connection = FakeConnection(
        signatures={"entries": signature, "preferences": signature},
        data_exists=True,
        invalid_dimensions=2,
    )
    client = _prepared_client(connection, schema_ensured=True)

    with pytest.raises(PgVectorDimensionError, match=r"2 vector\(s\)"):
        await client.ensure_collections(3, "openai", "model")


@pytest.mark.asyncio
async def test_recreate_is_one_transaction_and_publishes_fence_after_commit() -> None:
    connection = FakeConnection()
    client = _prepared_client(connection, schema_ensured=True)

    await client.recreate_collections(3, "openai", "model")

    truncate_position = next(
        index for index, sql in enumerate(connection.sql_calls) if sql.startswith("TRUNCATE")
    )
    drop_position = next(
        index for index, sql in enumerate(connection.sql_calls) if sql.startswith("DROP INDEX")
    )
    create_position = next(
        index for index, sql in enumerate(connection.sql_calls) if sql.startswith("CREATE INDEX")
    )
    assert truncate_position < drop_position < create_position
    assert (
        sum("INSERT INTO vector_store_metadata" in str(stmt) for stmt in connection.statements) == 2
    )
    assert client.check_model_compatibility(3, "openai", "model") == (True, None)


@pytest.mark.asyncio
async def test_failed_recreate_does_not_publish_new_fence() -> None:
    connection = FakeConnection(fail_hnsw=True)
    client = _prepared_client(connection, schema_ensured=True)
    client._last_model_signature = "openai:old:3"
    client._active_dimension = 3

    with pytest.raises(RuntimeError, match="index creation failed"):
        await client.recreate_collections(4, "openai", "new")

    assert client._last_model_signature == "openai:old:3"
    assert client._active_dimension == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        lambda client: client.insert_entry_embedding("entry", [1.0, 2.0], "feed"),
        lambda client: client.upsert_user_preference("user", "positive", [1.0, 2.0], 1, 1),
        lambda client: client.search_similar_entries([1.0, 2.0]),
    ],
)
async def test_vector_operations_reject_wrong_dimension(operation: Any) -> None:
    client = PgVectorClient()
    client._connected = True
    client._last_model_signature = "openai:model:3"
    client._active_dimension = 3
    _build_client_tables(client)

    with pytest.raises(PgVectorDimensionError, match="got 2, expected 3"):
        await operation(client)


@pytest.mark.asyncio
async def test_stale_writer_is_rejected_after_cross_process_rebuild() -> None:
    old_signature = "openai:old:3"
    session = FakeSession(signatures={"entries": "openai:new:3", "preferences": "openai:new:3"})
    client = PgVectorClient()
    client._connected = True
    client._last_model_signature = old_signature
    client._active_dimension = 3
    _build_client_tables(client)
    client._session_maker = lambda: session  # type: ignore[assignment]

    with pytest.raises(PgVectorModelMismatchError, match="changed while this job was running"):
        await client.insert_entry_embedding("entry", [1.0, 2.0, 3.0], "feed")

    assert not any("INSERT INTO entry_embeddings" in str(stmt) for stmt in session.statements)


@pytest.mark.asyncio
async def test_search_expression_casts_to_active_dimension_for_hnsw() -> None:
    signature = "openai:model:3"
    session = FakeSession(signatures={"entries": signature, "preferences": signature})
    client = PgVectorClient()
    client._connected = True
    client._last_model_signature = signature
    client._active_dimension = 3
    _build_client_tables(client)
    client._session_maker = lambda: session  # type: ignore[assignment]

    assert await client.search_similar_entries([1.0, 2.0, 3.0]) == []

    search_statement = next(
        statement
        for statement in session.statements
        if "ORDER BY" in str(statement) and "entry_embeddings" in str(statement)
    )
    assert "CAST(entry_embeddings.embedding AS VECTOR(3))" in str(search_statement)


@pytest.mark.asyncio
async def test_hnsw_index_matches_dimension_aware_search_expression() -> None:
    connection = FakeConnection()
    client = _prepared_client(connection, schema_ensured=True)

    await client._ensure_hnsw_index(connection, 1536)
    ddl = next(sql for sql in connection.sql_calls if sql.startswith("CREATE INDEX"))
    assert "embedding::vector(1536)" in ddl
    assert "vector_cosine_ops" in ddl


@pytest.mark.asyncio
async def test_hnsw_is_skipped_for_dimensions_unsupported_by_vector_opclass() -> None:
    connection = FakeConnection()
    client = _prepared_client(connection, schema_ensured=True)

    await client._ensure_hnsw_index(connection, 2001, replace=True)

    assert any(sql.startswith("DROP INDEX") for sql in connection.sql_calls)
    assert not any(sql.startswith("CREATE INDEX") for sql in connection.sql_calls)
