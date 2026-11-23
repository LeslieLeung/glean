"""Add persisted Jev entry classification.

Revision ID: c31f85d7a902
Revises: a9d4c1e82b70
"""

from alembic import op
import sqlalchemy as sa

revision = "c31f85d7a902"
down_revision = "a9d4c1e82b70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entries",
        sa.Column("classification_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column("entries", sa.Column("classification_result", sa.JSON(), nullable=True))
    op.add_column("entries", sa.Column("classification_error", sa.Text(), nullable=True))
    op.add_column("entries", sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_entries_classification_status", "entries", ["classification_status"])


def downgrade() -> None:
    op.drop_index("ix_entries_classification_status", table_name="entries")
    for column in (
        "classified_at",
        "classification_error",
        "classification_result",
        "classification_status",
    ):
        op.drop_column("entries", column)
