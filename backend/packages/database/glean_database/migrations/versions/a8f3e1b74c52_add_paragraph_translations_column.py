"""add paragraph_translations column

Revision ID: a8f3e1b74c52
Revises: 23b12d284237
Create Date: 2025-02-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8f3e1b74c52"
down_revision: Union[str, None] = "23b12d284237"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entry_translations",
        sa.Column("paragraph_translations", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entry_translations", "paragraph_translations")
