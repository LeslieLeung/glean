"""Regression tests for the optional pgvector Alembic migration."""

from unittest.mock import Mock, call

import pytest

from glean_database.migrations.versions import (
    b51dbf4f4d2a_add_pgvector_backend_tables as migration,
)


def test_upgrade_is_safe_when_database_has_no_vector_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_table = Mock()
    create_index = Mock()
    monkeypatch.setattr(migration, "_vector_extension_installed", lambda: False)
    monkeypatch.setattr(migration.op, "create_table", create_table)
    monkeypatch.setattr(migration.op, "create_index", create_index)

    migration.upgrade()

    create_table.assert_not_called()
    create_index.assert_not_called()


def test_upgrade_is_idempotent_when_runtime_already_created_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_table = Mock()
    create_index = Mock()
    monkeypatch.setattr(migration, "_vector_extension_installed", lambda: True)
    monkeypatch.setattr(migration, "_has_table", lambda _name: True)
    monkeypatch.setattr(migration, "_has_index", lambda _table, _index: True)
    monkeypatch.setattr(migration.op, "create_table", create_table)
    monkeypatch.setattr(migration.op, "create_index", create_index)

    migration.upgrade()

    create_table.assert_not_called()
    create_index.assert_not_called()


def test_downgrade_drops_optional_schema_regardless_of_active_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock()
    monkeypatch.setattr(migration.op, "execute", execute)
    monkeypatch.setenv("VECTOR_BACKEND", "milvus")

    migration.downgrade()

    assert execute.call_args_list == [
        call("DROP TABLE IF EXISTS vector_store_metadata"),
        call("DROP TABLE IF EXISTS user_preference_vectors"),
        call("DROP TABLE IF EXISTS entry_embeddings"),
    ]
