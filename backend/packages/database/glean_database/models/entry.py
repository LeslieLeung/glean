"""
Entry model definition.

This module defines the Entry model for storing feed entries (articles).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class Entry(Base, TimestampMixin):
    """
    Feed entry (article) model.

    Stores individual entries from RSS feeds. Entries are shared
    globally and linked to user-specific state via UserEntry.

    Attributes:
        id: Unique entry identifier (UUID).
        feed_id: Parent feed reference.
        url: Entry URL (indexed for deduplication).
        title: Entry title.
        author: Entry author name.
        content: Full entry content (HTML).
        summary: Entry summary or excerpt.
        guid: Original entry GUID for deduplication.
        published_at: Original publication timestamp.
    """

    __tablename__ = "entries"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Parent feed reference
    feed_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Entry content
    url: Mapped[str] = mapped_column(String(2000), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)

    # Metadata
    guid: Mapped[str | None] = mapped_column(String(500), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # M3: Embedding status
    embedding_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # pending / processing / done / failed
    embedding_error: Mapped[str | None] = mapped_column(Text)
    embedding_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    word_count: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    feed = relationship("Feed", back_populates="entries")
    user_entries = relationship("UserEntry", back_populates="entry", cascade="all, delete-orphan")
    bookmarks = relationship("Bookmark", back_populates="entry")

    # Constraints: Unique entry per feed
    __table_args__ = (UniqueConstraint("feed_id", "guid", name="uq_feed_guid"),)
