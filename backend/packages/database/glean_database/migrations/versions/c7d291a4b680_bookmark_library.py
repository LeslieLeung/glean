"""Preserve bookmark content and metadata ownership.

Revision ID: c7d291a4b680
Revises: a9d4c1e82b70
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d291a4b680"
down_revision = "a9d4c1e82b70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookmarks", sa.Column("source_type", sa.String(20), nullable=False, server_default="external"))
    op.add_column("bookmarks", sa.Column("source_name", sa.String(500), nullable=True))
    op.add_column("bookmarks", sa.Column("title_edited", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("bookmarks", sa.Column("excerpt_edited", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("""UPDATE bookmarks b SET source_type = 'rss', source_name = LEFT(f.title, 500),
        url = COALESCE(b.url, e.url), content = COALESCE(b.content, e.content),
        excerpt = COALESCE(b.excerpt, e.summary)
        FROM entries e JOIN feeds f ON f.id = e.feed_id WHERE b.entry_id = e.id""")
    op.execute("""UPDATE bookmarks SET
        title_edited = (title IS DISTINCT FROM url), excerpt_edited = (excerpt IS NOT NULL),
        snapshot_status = CASE WHEN content IS NOT NULL OR source_type = 'rss' THEN 'done' ELSE 'failed' END""")


def downgrade() -> None:
    for column in ("excerpt_edited", "title_edited", "source_name", "source_type"):
        op.drop_column("bookmarks", column)
