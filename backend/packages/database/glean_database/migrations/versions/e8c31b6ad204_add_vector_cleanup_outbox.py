"""add durable vector cleanup outbox

Revision ID: e8c31b6ad204
Revises: d6a4f28e91c3
Create Date: 2026-07-28 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8c31b6ad204"
down_revision: str | None = "d6a4f28e91c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vector_cleanup_pending",
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("feed_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    op.create_index(
        "ix_vector_cleanup_pending_feed_id",
        "vector_cleanup_pending",
        ["feed_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vector_cleanup_pending_feed_id",
        table_name="vector_cleanup_pending",
    )
    op.drop_table("vector_cleanup_pending")
