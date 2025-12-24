"""
Bookmark model definition.

This module defines the Bookmark model for saving entries and external URLs.
"""

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class Bookmark(Base, TimestampMixin):
    """
    Bookmark model for saving content.

    Supports both system entries and external URLs.

    Attributes:
        id: Unique bookmark identifier (UUID).
        user_id: Owner user reference.
        entry_id: Reference to system entry (optional).
        url: External URL (optional, required if entry_id is null).
        title: Bookmark title.
        excerpt: Optional excerpt/summary.
        content: Full article content (HTML) extracted from URL.
        snapshot_status: Status of content snapshot (pending/processing/done/failed).
        snapshot_path: Path to stored snapshot (M6 feature).
    """

    __tablename__ = "bookmarks"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Foreign keys
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Bookmark content
    url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)  # Full article content (HTML)

    # Snapshot status (for M6)
    snapshot_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    snapshot_path: Mapped[str | None] = mapped_column(String(500))

    # Relationships
    user = relationship("User", back_populates="bookmarks")
    entry = relationship("Entry", back_populates="bookmarks")
    bookmark_folders = relationship(
        "BookmarkFolder", back_populates="bookmark", cascade="all, delete-orphan"
    )
    bookmark_tags = relationship(
        "BookmarkTag", back_populates="bookmark", cascade="all, delete-orphan"
    )

    # Constraints: Either entry_id or url must be provided
    # Unique constraint: one bookmark per user per entry (when entry_id is set)
    __table_args__ = (
        CheckConstraint(
            "(entry_id IS NOT NULL) OR (url IS NOT NULL)",
            name="ck_bookmark_source",
        ),
        CheckConstraint(
            "snapshot_status IN ('pending', 'processing', 'done', 'failed')",
            name="ck_snapshot_status",
        ),
        # Partial unique index: only one bookmark per user per entry
        Index(
            "ix_bookmarks_user_entry_unique",
            "user_id",
            "entry_id",
            unique=True,
            postgresql_where="entry_id IS NOT NULL",
        ),
    )
