"""Replace missing and future publication times with fetch time.

Revision ID: a9d4c1e82b70
Revises: f2b67e19a830
Create Date: 2026-11-04 00:00:00.000000

Entries with no feed date sort first under ``ORDER BY published_at DESC``
because PostgreSQL puts nulls first. Dates far in the future stay pinned
the same way. Both are stored as ``created_at``, the time the article was
pulled. The 15 minute allowance matches
``glean_core.published_at.FUTURE_PUBLISHED_AT_TOLERANCE``.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a9d4c1e82b70"
down_revision: str | None = "f2b67e19a830"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE entries
        SET published_at = created_at
        WHERE published_at IS NULL
           OR published_at > CURRENT_TIMESTAMP + INTERVAL '15 minutes'
        """
    )
    op.execute(
        """
        UPDATE feeds AS f
        SET last_entry_at = src.max_published
        FROM (
            SELECT feed_id, MAX(published_at) AS max_published
            FROM entries
            GROUP BY feed_id
        ) AS src
        WHERE f.id = src.feed_id
          AND f.last_entry_at IS NOT NULL
          AND f.last_entry_at > CURRENT_TIMESTAMP + INTERVAL '15 minutes'
        """
    )


def downgrade() -> None:
    # The original feed timestamps were overwritten and cannot be restored.
    pass
