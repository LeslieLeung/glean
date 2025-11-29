"""
Feed model definition.

This module defines the Feed model for storing RSS feed information.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class FeedStatus(str, Enum):
    """Feed status enumeration."""

    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class Feed(Base, TimestampMixin):
    """
    RSS feed model.

    Stores feed metadata and fetch status. Feeds are shared globally
    across all users to avoid duplicate fetching.

    Attributes:
        id: Unique feed identifier (UUID).
        url: Feed URL (unique, indexed).
        title: Feed title from source.
        site_url: Website URL associated with feed.
        description: Feed description.
        icon_url: Favicon or feed icon URL.
        status: Current feed status.
        error_count: Consecutive fetch error count.
        last_fetched_at: Timestamp of last successful fetch.
        etag: HTTP ETag for conditional requests.
        last_modified: HTTP Last-Modified header value.
    """

    __tablename__ = "feeds"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )

    # Feed metadata
    url: Mapped[str] = mapped_column(
        String(2000), unique=True, nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500))
    site_url: Mapped[str | None] = mapped_column(String(2000))
    description: Mapped[str | None] = mapped_column(String(2000))
    icon_url: Mapped[str | None] = mapped_column(String(500))

    # Fetch status
    status: Mapped[FeedStatus] = mapped_column(
        String(20), default=FeedStatus.ACTIVE, nullable=False
    )
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Conditional request headers
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    entries = relationship(
        "Entry", back_populates="feed", cascade="all, delete-orphan"
    )
    subscriptions = relationship(
        "Subscription", back_populates="feed", cascade="all, delete-orphan"
    )
