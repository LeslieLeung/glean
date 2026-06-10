"""add_entry_translations_table

Revision ID: 23b12d284237
Revises: 4c4ef51cbb46
Create Date: 2026-02-08 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "23b12d284237"
down_revision: Union[str, None] = "4c4ef51cbb46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entry_translations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("target_language", sa.String(length=10), nullable=False),
        sa.Column("translated_title", sa.String(length=1000), nullable=True),
        sa.Column("translated_content", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entry_id", "target_language", name="uq_entry_translation_lang"
        ),
    )
    op.create_index(
        op.f("ix_entry_translations_entry_id"),
        "entry_translations",
        ["entry_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_entry_translations_entry_id"),
        table_name="entry_translations",
    )
    op.drop_table("entry_translations")
