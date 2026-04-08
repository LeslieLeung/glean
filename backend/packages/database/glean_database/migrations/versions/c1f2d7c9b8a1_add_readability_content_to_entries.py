"""add_readability_content_to_entries

Revision ID: c1f2d7c9b8a1
Revises: 7c6b419ed52d
Create Date: 2026-04-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f2d7c9b8a1"
down_revision: str | None = "7c6b419ed52d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("entries", sa.Column("readability_content", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("entries", "readability_content")
