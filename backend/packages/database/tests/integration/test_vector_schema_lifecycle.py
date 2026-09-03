"""Real PostgreSQL regression tests for the optional vector schema lifecycle.

These tests are intentionally opt-in because they reset the ``public`` schema.
CI runs each scenario in an isolated PostgreSQL service by setting
``RUN_VECTOR_SCHEMA_TESTS=1`` and selecting one test with ``pytest -k``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_VECTOR_SCHEMA_TESTS") != "1",
    reason="destructive vector schema integration tests are opt-in",
)

_DATABASE_PACKAGE = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _DATABASE_PACKAGE / "alembic.ini"
_MIGRATIONS = _DATABASE_PACKAGE / "glean_database" / "migrations"
_PRE_PGVECTOR_REVISION = "7c6b419ed52d"
_VECTOR_TABLES = {
    "entry_embeddings",
    "user_preference_vectors",
    "vector_store_metadata",
}


def _database_url() -> str:
    value = os.environ["VECTOR_SCHEMA_DATABASE_URL"]
    database_name = make_url(value).database or ""
    if "test" not in database_name:
        raise RuntimeError(
            "VECTOR_SCHEMA_DATABASE_URL must target a database whose name contains 'test'"
        )
    return value


def _run_async(awaitable: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(awaitable)


def _alembic_config() -> Config:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_MIGRATIONS))
    config.set_main_option("sqlalchemy.url", _database_url())
    return config


def _head_revision() -> str:
    revision = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    assert revision is not None
    return revision


def _upgrade(revision: str, *, backend: str) -> None:
    os.environ["DATABASE_URL"] = _database_url()
    os.environ["VECTOR_BACKEND"] = backend
    command.upgrade(_alembic_config(), revision)


def _downgrade(revision: str, *, backend: str) -> None:
    os.environ["DATABASE_URL"] = _database_url()
    os.environ["VECTOR_BACKEND"] = backend
    command.downgrade(_alembic_config(), revision)


async def _with_connection(callback: Any) -> Any:
    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as connection:
            return await callback(connection)
    finally:
        await engine.dispose()


async def _reset_database() -> None:
    async def reset(connection: AsyncConnection) -> None:
        await connection.execute(text("DROP EXTENSION IF EXISTS vector CASCADE"))
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))

    await _with_connection(reset)


async def _install_vector_extension() -> None:
    async def install(connection: AsyncConnection) -> None:
        await connection.execute(text("CREATE EXTENSION vector"))

    await _with_connection(install)


async def _revision() -> str:
    async def read_revision(connection: AsyncConnection) -> str:
        result = await connection.execute(text("SELECT version_num FROM alembic_version"))
        return str(result.scalar_one())

    return str(await _with_connection(read_revision))


async def _existing_vector_tables() -> set[str]:
    async def read_tables(connection: AsyncConnection) -> set[str]:
        result = await connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(:table_names)"
            ),
            {"table_names": sorted(_VECTOR_TABLES)},
        )
        return {str(row[0]) for row in result}

    return set(await _with_connection(read_tables))


async def _assert_core_schema_exists() -> None:
    async def assert_core_schema(connection: AsyncConnection) -> None:
        result = await connection.execute(text("SELECT to_regclass('public.entries')"))
        assert result.scalar_one() == "entries"

    await _with_connection(assert_core_schema)


async def _assert_runtime_vector_schema(signature: str) -> None:
    async def assert_schema(connection: AsyncConnection) -> None:
        extension = await connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        assert extension.scalar_one() is True

        metadata = await connection.execute(
            text("SELECT name, model_signature FROM vector_store_metadata ORDER BY name")
        )
        assert metadata.all() == [
            ("entries", signature),
            ("preferences", signature),
        ]

        hnsw_index = await connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "AND tablename = 'entry_embeddings' "
                "AND indexname = 'ix_entry_embeddings_embedding_hnsw'"
            )
        )
        index_definition = str(hnsw_index.scalar_one())
        assert "USING hnsw" in index_definition
        assert "vector(3)" in index_definition
        assert "vector_cosine_ops" in index_definition

        foreign_key = await connection.execute(
            text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conrelid = 'entry_embeddings'::regclass "
                "AND confrelid = 'entries'::regclass "
                "AND contype = 'f'"
            )
        )
        assert foreign_key.scalar_one() == 1

    assert await _existing_vector_tables() == _VECTOR_TABLES
    await _with_connection(assert_schema)


async def _runtime_provision() -> None:
    # Import only after the test database URL has been installed in the
    # environment. This keeps the integration test independent of a local .env.
    client = _runtime_client()
    try:
        await client.ensure_collections(3, "ci", "schema-test")
    finally:
        await client.disconnect()


def _runtime_client() -> Any:
    """Build a pgvector client bound to the isolated schema test database."""
    from glean_vector.clients.pgvector_client import PgVectorClient
    from glean_vector.config import PgVectorConfig

    client = PgVectorClient()
    client.config = PgVectorConfig(
        database_url=_database_url(),
        entries_table="entry_embeddings",
        prefs_table="user_preference_vectors",
        metadata_table="vector_store_metadata",
    )
    return client


async def _insert_relational_entries() -> None:
    async def insert_rows(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                "INSERT INTO feeds (id, url, status, error_count) VALUES "
                "('feed-a', 'https://example.com/feed-a', 'active', 0)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO entries (id, feed_id, url, title) VALUES "
                "('entry-a', 'feed-a', 'https://example.com/a', 'Entry A'), "
                "('entry-b', 'feed-a', 'https://example.com/b', 'Entry B')"
            )
        )

    await _with_connection(insert_rows)


def test_fresh_pgvector_migration_and_runtime_are_compatible() -> None:
    """A fresh pgvector install gets migration-managed tables and runtime metadata."""
    _run_async(_reset_database())
    _run_async(_install_vector_extension())

    _upgrade("head", backend="pgvector")

    assert _run_async(_revision()) == _head_revision()
    assert _run_async(_existing_vector_tables()) == _VECTOR_TABLES

    _run_async(_runtime_provision())

    _run_async(_assert_runtime_vector_schema("ci:schema-test:3"))


def test_runtime_provision_after_milvus_upgrade_without_pgvector_schema() -> None:
    """Switching an upgraded Milvus database to pgvector provisions missing schema."""
    _run_async(_reset_database())

    _upgrade("head", backend="milvus")

    assert _run_async(_revision()) == _head_revision()
    _run_async(_assert_core_schema_exists())
    assert _run_async(_existing_vector_tables()) == set()

    _run_async(_runtime_provision())

    assert _run_async(_revision()) == _head_revision()
    _run_async(_assert_runtime_vector_schema("ci:schema-test:3"))


def test_cross_backend_downgrade_and_reupgrade_restores_pgvector_schema() -> None:
    """Downgrade under Milvus and re-upgrade under pgvector is deterministic."""
    _run_async(_reset_database())
    _run_async(_install_vector_extension())
    _upgrade("head", backend="pgvector")
    assert _run_async(_existing_vector_tables()) == _VECTOR_TABLES

    _downgrade(_PRE_PGVECTOR_REVISION, backend="milvus")

    assert _run_async(_revision()) == _PRE_PGVECTOR_REVISION
    _run_async(_assert_core_schema_exists())
    assert _run_async(_existing_vector_tables()) == set()

    _upgrade("head", backend="pgvector")

    assert _run_async(_revision()) == _head_revision()
    assert _run_async(_existing_vector_tables()) == _VECTOR_TABLES
    _run_async(_runtime_provision())
    _run_async(_assert_runtime_vector_schema("ci:schema-test:3"))


def test_pgvector_crud_search_and_generation_fence() -> None:
    """Real pgvector reads/writes use the active dimension and reject stale clients."""

    _run_async(_reset_database())
    _run_async(_install_vector_extension())
    _upgrade("head", backend="pgvector")
    _run_async(_insert_relational_entries())

    async def exercise() -> None:
        from glean_vector.clients.pgvector_client import PgVectorModelMismatchError

        first = _runtime_client()
        second = _runtime_client()
        try:
            await first.ensure_collections(3, "ci", "schema-test")
            await first.insert_entry_embedding(
                "entry-a",
                [1.0, 0.0, 0.0],
                "feed-a",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                language="en",
                word_count=10,
                author="A",
            )
            await first.insert_entry_embedding(
                "entry-b",
                [0.0, 1.0, 0.0],
                "feed-a",
                published_at=datetime(2026, 1, 2, tzinfo=UTC),
                language="en",
                word_count=20,
                author="B",
            )
            assert await first.get_entry_embedding("entry-a") == [1.0, 0.0, 0.0]
            assert await first.batch_get_entry_embeddings(["entry-a", "entry-b"]) == {
                "entry-a": [1.0, 0.0, 0.0],
                "entry-b": [0.0, 1.0, 0.0],
            }

            matches = await first.search_similar_entries([1.0, 0.0, 0.0], top_k=2)
            assert [match["id"] for match in matches] == ["entry-a", "entry-b"]
            assert matches[0]["score"] == pytest.approx(1.0)

            await first.upsert_user_preference(
                "user-a",
                "positive",
                [0.5, 0.5, 0.0],
                sample_count=2.0,
                updated_at=1,
            )
            preferences = await first.get_user_preferences("user-a")
            assert preferences["positive"]["embedding"] == [0.5, 0.5, 0.0]
            await first.delete_user_preferences("user-a")
            assert await first.get_user_preferences("user-a") == {}

            # A second process can replace the store generation. The first
            # client's cached signature must not authorize a stale write.
            await second.ensure_collections(3, "ci", "schema-test")
            await second.recreate_collections(3, "ci", "schema-next")
            with pytest.raises(PgVectorModelMismatchError):
                await first.delete_entry_embedding("entry-a")

            await second.insert_entry_embedding(
                "entry-a",
                [1.0, 0.0, 0.0],
                "feed-a",
            )
            await second.delete_entry_embedding("entry-a")
            assert await second.get_entry_embedding("entry-a") is None
        finally:
            await first.disconnect()
            await second.disconnect()

    _run_async(exercise())
