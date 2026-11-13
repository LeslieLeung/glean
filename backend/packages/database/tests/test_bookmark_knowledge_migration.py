"""Verify the personal knowledge schema, indexed backfill and safe rollback."""

from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from glean_database.migrations.versions import d84b1a7c902e_bookmark_knowledge as migration


async def test_knowledge_migration_backfills_batches_and_rolls_back(db_session, monkeypatch):
    schema = "bookmark_knowledge_" + uuid4().hex
    connection = await db_session.connection()
    await connection.execute(text(f"CREATE SCHEMA {schema}"))
    await connection.execute(text(f"SET LOCAL search_path TO {schema}, public"))
    await connection.execute(
        text("""CREATE TABLE bookmarks (
        id varchar(36) PRIMARY KEY, title text NOT NULL, excerpt text, url text,
        source_name text, content text)""")
    )
    await connection.execute(
        text("""INSERT INTO bookmarks
        SELECT lpad(n::text, 36, '0'), 'Title', '<p>Summary &amp; details</p>',
        'https://example.org/' || n, 'Source', '<p>中文正文 &#128512;</p><script>hidden</script>'
        FROM generate_series(1, 501) n""")
    )

    def upgrade(sync_connection):
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(sync_connection))
        )
        migration.upgrade()

    await connection.run_sync(upgrade)
    assert (
        await connection.scalar(
            text(
                "SELECT count(*) FROM bookmarks WHERE search_text LIKE '%中文正文 😀%' AND search_text NOT LIKE '%hidden%'"
            )
        )
        == 501
    )
    assert (
        await connection.scalar(
            text("SELECT count(*) FROM bookmarks WHERE search_text LIKE '%Summary & details%'")
        )
        == 501
    )
    indexes = (
        (
            await connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :schema"),
                {"schema": schema},
            )
        )
        .scalars()
        .all()
    )
    assert {
        "ix_bookmarks_search_text",
        "ix_bookmark_notes_body",
        "ix_bookmark_annotations_search_text",
    } <= set(indexes)
    bookmark_id = "1".rjust(36, "0")
    await connection.execute(
        text("INSERT INTO bookmark_notes (bookmark_id, body, revision) VALUES (:id, 'Note', 1)"),
        {"id": bookmark_id},
    )
    await connection.execute(text("DELETE FROM bookmarks WHERE id = :id"), {"id": bookmark_id})
    assert await connection.scalar(text("SELECT count(*) FROM bookmark_notes")) == 0
    await connection.run_sync(lambda _: migration.downgrade())
    assert await connection.scalar(text("SELECT count(*) FROM bookmarks")) == 500
    assert (
        await connection.scalar(text("SELECT content FROM bookmarks LIMIT 1"))
        == "<p>中文正文 &#128512;</p><script>hidden</script>"
    )
