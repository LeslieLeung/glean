"""Exercise bookmark backfill and rollback against PostgreSQL."""

from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from glean_database.migrations.versions import c7d291a4b680_bookmark_library as migration


async def test_bookmark_backfill_and_downgrade(db_session, monkeypatch):
    schema = "bookmark_migration_" + uuid4().hex
    connection = await db_session.connection()
    await connection.execute(text(f"CREATE SCHEMA {schema}"))
    await connection.execute(text(f"SET LOCAL search_path TO {schema}"))
    await connection.execute(text("CREATE TABLE feeds (id text PRIMARY KEY, title text)"))
    await connection.execute(
        text(
            "CREATE TABLE entries (id text PRIMARY KEY, feed_id text, url text, content text, summary text)"
        )
    )
    await connection.execute(
        text(
            "CREATE TABLE bookmarks (id text PRIMARY KEY, entry_id text, url text, title text, content text, excerpt text, snapshot_status text)"
        )
    )
    await connection.execute(text("INSERT INTO feeds VALUES ('f', 'Original feed')"))
    await connection.execute(
        text(
            "INSERT INTO entries VALUES ('e', 'f', 'https://example.org/article', '<p>Original body</p>', 'Summary')"
        )
    )
    await connection.execute(
        text(
            "INSERT INTO bookmarks VALUES ('b', 'e', NULL, 'Edited title', NULL, NULL, 'pending'), ('external', NULL, 'https://example.org/link', 'Custom', NULL, 'Custom summary', 'pending')"
        )
    )

    def upgrade(sync_connection):
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(sync_connection))
        )
        migration.upgrade()

    await connection.run_sync(upgrade)
    result = (
        (await connection.execute(text("SELECT * FROM bookmarks WHERE id = 'b'"))).mappings().one()
    )
    assert result["content"] == "<p>Original body</p>"
    assert result["url"] == "https://example.org/article"
    assert result["title"] == "Edited title"
    assert result["source_type"] == "rss"
    assert result["source_name"] == "Original feed"
    assert result["snapshot_status"] == "done"
    assert result["title_edited"] is True
    external = (
        (await connection.execute(text("SELECT * FROM bookmarks WHERE id = 'external'")))
        .mappings()
        .one()
    )
    assert external["excerpt_edited"] is True
    assert external["snapshot_status"] == "failed"
    await connection.run_sync(lambda _: migration.downgrade())
    assert (
        await connection.scalar(text("SELECT content FROM bookmarks WHERE id = 'b'"))
        == "<p>Original body</p>"
    )
