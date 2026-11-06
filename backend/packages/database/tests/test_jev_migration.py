"""Verify classification migration defaults and reversible schema changes."""

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from glean_database.migrations.versions import c31f85d7a902_add_entry_classification as migration


async def test_existing_and_new_entries_default_to_pending_and_downgrade_preserves_rows(
    test_engine,
):
    def exercise(connection):
        # A temporary table shadows the real entries table for this connection.
        connection.execute(text("CREATE TEMP TABLE entries (id TEXT PRIMARY KEY) ON COMMIT DROP"))
        connection.execute(text("INSERT INTO entries (id) VALUES ('existing')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            connection.execute(text("INSERT INTO entries (id) VALUES ('new')"))
            rows = connection.execute(
                text(
                    "SELECT id, classification_status, classification_result, classification_error, classified_at FROM entries ORDER BY id"
                )
            ).all()
            assert rows == [
                ("existing", "pending", None, None, None),
                ("new", "pending", None, None, None),
            ]
            migration.downgrade()
            assert connection.execute(
                text("SELECT id FROM entries ORDER BY id")
            ).scalars().all() == ["existing", "new"]

    async with test_engine.begin() as connection:
        await connection.run_sync(exercise)
