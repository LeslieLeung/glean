"""add_pgvector_backend_tables

Revision ID: b51dbf4f4d2a
Revises: 7c6b419ed52d
Create Date: 2026-02-13 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - migration runtime dependency
    Vector = None  # type: ignore[assignment,misc]

# revision identifiers, used by Alembic.
revision: str = "b51dbf4f4d2a"
down_revision: str | None = "7c6b419ed52d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if Vector is None:
        raise RuntimeError("pgvector is required to run this migration")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "entry_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),  # type: ignore[misc]
        sa.Column("feed_id", sa.String(length=36), nullable=False),
        sa.Column("published_at", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("author", sa.String(length=200), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["id"], ["entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entry_embeddings_feed_id", "entry_embeddings", ["feed_id"], unique=False)
    op.create_index(
        "ix_entry_embeddings_published_at",
        "entry_embeddings",
        ["published_at"],
        unique=False,
    )
    # HNSW index requires fixed-dimension vector columns. We intentionally keep
    # vector columns dimension-agnostic here to support model switches and handle
    # optional index creation at runtime.

    op.create_table(
        "user_preference_vectors",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("vector_type", sa.String(length=20), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),  # type: ignore[misc]
        sa.Column("sample_count", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "vector_type", name="uq_user_vector_type"),
    )
    op.create_index(
        "ix_user_preference_vectors_user_id",
        "user_preference_vectors",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "vector_store_metadata",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("model_signature", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("vector_store_metadata")
    op.drop_index("ix_user_preference_vectors_user_id", table_name="user_preference_vectors")
    op.drop_table("user_preference_vectors")
    op.execute("DROP INDEX IF EXISTS idx_entry_embeddings_embedding_hnsw")
    op.drop_index("ix_entry_embeddings_published_at", table_name="entry_embeddings")
    op.drop_index("ix_entry_embeddings_feed_id", table_name="entry_embeddings")
    op.drop_table("entry_embeddings")
