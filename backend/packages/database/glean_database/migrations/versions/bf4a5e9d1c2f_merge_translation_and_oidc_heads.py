"""merge translation and oidc heads

Revision ID: bf4a5e9d1c2f
Revises: a8f3e1b74c52, 7c6b419ed52d
Create Date: 2026-02-15 00:00:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "bf4a5e9d1c2f"
down_revision: Union[str, Sequence[str], None] = ("a8f3e1b74c52", "7c6b419ed52d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
