"""
UserEntry model definition.

This module defines the UserEntry model for user-specific entry state.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class UserEntry(Base, TimestampMixin):
    """
    User-specific entry state model.

    Tracks read status, likes, and other user-specific data
    for each entry a user has interacted with.

    Attributes:
        id: Unique record identifier (UUID).
        user_id: User reference.
        entry_id: Entry reference.
        is_read: Whether user has read the entry.
        is_liked: User's like status (True/False/None).
        read_later: Whether marked for later reading.
        preference_score: Computed preference score for recommendations.
        read_at: Timestamp when marked as read.
        liked_at: Timestamp when liked/disliked.
    """

    __tablename__ = "user_entries"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )

    # Foreign keys
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # User state
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_liked: Mapped[bool | None] = mapped_column(Boolean)
    read_later: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Recommendation data
    preference_score: Mapped[float | None] = mapped_column(Float)

    # Timestamps
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    liked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="user_entries")
    entry = relationship("Entry", back_populates="user_entries")

    # Constraints: One record per user-entry pair
    __table_args__ = (
        UniqueConstraint("user_id", "entry_id", name="uq_user_entry"),
    )
