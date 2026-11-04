"""Track the last successful feed fetch separately from attempts.

Revision ID: f2b67e19a830
Revises: e8c31b6ad204
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b67e19a830"
down_revision: str | None = "e8c31b6ad204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Historical attempt timestamps cannot establish a last successful fetch.
    op.add_column("feeds", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("feeds", "last_success_at")
