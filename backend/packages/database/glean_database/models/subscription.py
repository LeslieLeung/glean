"""
Subscription model definition.

This module defines the Subscription model for user-feed associations.
"""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class Subscription(Base, TimestampMixin):
    """
    User-feed subscription model.

    Links users to feeds they have subscribed to, with optional
    customization like custom titles.

    Attributes:
        id: Unique subscription identifier (UUID).
        user_id: Subscribing user reference.
        feed_id: Subscribed feed reference.
        custom_title: User-defined title override.
    """

    __tablename__ = "subscriptions"

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
    feed_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Customization
    custom_title: Mapped[str | None] = mapped_column(String(500))

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    feed = relationship("Feed", back_populates="subscriptions")

    # Constraints: User can only subscribe to a feed once
    __table_args__ = (
        UniqueConstraint("user_id", "feed_id", name="uq_user_feed"),
    )
