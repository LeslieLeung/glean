"""Durable outbox rows for orphaned vector cleanup."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class VectorCleanupPending(Base, TimestampMixin):
    """An entry deleted from PostgreSQL that must be removed from vector storage."""

    __tablename__ = "vector_cleanup_pending"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    feed_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
