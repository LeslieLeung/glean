"""add_pgvector_backend_tables

Revision ID: b51dbf4f4d2a
Revises: 7c6b419ed52d
Create Date: 2026-02-13 10:00:00.000000

"""

import os
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


def _is_pgvector_backend() -> bool:
    """Return whether the pgvector vector backend is active.

    The pgvector schema (the ``vector`` extension plus the embedding tables) is
    only provisioned when the deployment is configured to use the pgvector
    backend.  Milvus (the default) and any other backend skip it entirely so
    those deployments are not forced to have the ``vector`` extension available
    on their PostgreSQL server.  This mirrors ``VectorBackendConfig`` whose
    default is ``"milvus"``.
    """
    return os.getenv("VECTOR_BACKEND", "milvus").strip().lower() == "pgvector"


def upgrade() -> None:
    # Milvus / non-pgvector deployments: pgvector schema is not needed.
    if not _is_pgvector_backend():
        return

    if Vector is None:
        raise RuntimeError("pgvector is required to apply pgvector schema migration")

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
    # Mirror upgrade(): only the pgvector backend ever created this schema.
    # Use IF EXISTS throughout so the downgrade is a safe no-op when the tables
    # were never provisioned (e.g. Milvus deployments).
    if not _is_pgvector_backend():
        return

    # Dropping each table also removes its associated indexes.
    op.execute("DROP TABLE IF EXISTS vector_store_metadata")
    op.execute("DROP TABLE IF EXISTS user_preference_vectors")
    op.execute("DROP TABLE IF EXISTS entry_embeddings")
