"""Bookmark notes, anchored annotations and indexed content search.

Revision ID: d84b1a7c902e
Revises: c7d291a4b680
"""
from alembic import op
import sqlalchemy as sa

from glean_database.search_text import bookmark_search_text

revision = "d84b1a7c902e"
down_revision = "c7d291a4b680"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
            for name in ("created_at", "updated_at")]


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("Bookmark search backfill requires an online migration connection")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column("bookmarks", sa.Column("search_text", sa.Text(), nullable=False, server_default=""))
    op.create_table("bookmark_notes",
        sa.Column("bookmark_id", sa.String(36), sa.ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), *timestamps())
    op.create_table("bookmark_annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bookmark_id", sa.String(36), sa.ForeignKey("bookmarks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exact", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("suffix", sa.Text(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("anchor_version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("color", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.CheckConstraint('"end" > start AND start >= 0', name="ck_annotation_position"),
        sa.CheckConstraint("color IN ('yellow', 'green', 'blue', 'pink')", name="ck_annotation_color"),
        *timestamps())
    op.create_index("ix_bookmark_annotations_bookmark_id", "bookmark_annotations", ["bookmark_id"])
    # Bounded keyset backfill; HTML entities are decoded with the same projection as writes.
    connection = op.get_bind()
    last_id = ""
    while True:
        rows = connection.execute(sa.text("""SELECT id, title, excerpt, url, source_name, content
            FROM bookmarks WHERE id > :last_id ORDER BY id LIMIT 500"""), {"last_id": last_id}).mappings().all()
        if not rows:
            break
        connection.execute(sa.text("UPDATE bookmarks SET search_text = :search_text WHERE id = :id"), [
            {"id": row["id"], "search_text": bookmark_search_text(row["title"], row["excerpt"], row["url"], row["source_name"], row["content"])}
            for row in rows
        ])
        last_id = rows[-1]["id"]
    for table, column in (("bookmarks", "search_text"), ("bookmark_notes", "body"), ("bookmark_annotations", "search_text")):
        op.create_index(f"ix_{table}_{column}", table, [column], postgresql_using="gin", postgresql_ops={column: "gin_trgm_ops"})


def downgrade() -> None:
    op.drop_table("bookmark_annotations")
    op.drop_table("bookmark_notes")
    op.drop_index("ix_bookmarks_search_text", table_name="bookmarks")
    op.drop_column("bookmarks", "search_text")
