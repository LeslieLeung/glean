"""
EntryEmbedding model definition.

Stores entry vectors in PostgreSQL pgvector backend.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import BIGINT, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EntryEmbedding(Base):
    """Entry embedding table for pgvector backend."""

    __tablename__ = "entry_embeddings"

    id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector())  # type: ignore[misc,valid-type]
    feed_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    published_at: Mapped[int] = mapped_column(BIGINT, nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    author: Mapped[str] = mapped_column(String(200), nullable=False, default="")
