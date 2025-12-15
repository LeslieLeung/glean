"""
Entry schemas.

Request and response models for entry-related operations.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EntryBase(BaseModel):
    """Base entry fields."""

    title: str
    url: str


class EntryResponse(BaseModel):
    """Entry response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    feed_id: str
    url: str
    title: str
    author: str | None
    content: str | None
    summary: str | None
    published_at: datetime | None
    created_at: datetime
    # User-specific fields (from UserEntry)
    is_read: bool = False
    is_liked: bool | None = None
    read_later: bool = False
    read_later_until: datetime | None = None
    read_at: datetime | None = None
    is_bookmarked: bool = False
    bookmark_id: str | None = None
    # Preference score for recommendations (M3)
    preference_score: float | None = None
    # Feed info for display in aggregated views
    feed_title: str | None = None
    feed_icon_url: str | None = None


class EntryListResponse(BaseModel):
    """Paginated entry list response."""

    items: list[EntryResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class UpdateEntryStateRequest(BaseModel):
    """Update entry state request."""

    is_read: bool | None = None
    is_liked: bool | None = None
    read_later: bool | None = None
    # Days until read-later expires (0 = never expire)
    read_later_days: int | None = None
