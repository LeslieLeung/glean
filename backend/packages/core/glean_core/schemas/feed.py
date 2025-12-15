"""
Feed and subscription schemas.

Request and response models for feed-related operations.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class FeedBase(BaseModel):
    """Base feed fields."""

    url: HttpUrl
    title: str | None = None
    description: str | None = None


class FeedResponse(BaseModel):
    """Feed response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    title: str | None
    site_url: str | None
    description: str | None
    icon_url: str | None
    language: str | None
    status: str
    error_count: int
    last_fetched_at: datetime | None
    last_entry_at: datetime | None
    created_at: datetime


class SubscriptionResponse(BaseModel):
    """Subscription response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    feed_id: str
    custom_title: str | None
    folder_id: str | None = None
    created_at: datetime
    feed: FeedResponse
    unread_count: int = 0


class DiscoverFeedRequest(BaseModel):
    """Discover feed from URL request."""

    url: HttpUrl
    folder_id: str | None = None


class UpdateSubscriptionRequest(BaseModel):
    """Update subscription request.

    Note: folder_id uses a special sentinel to distinguish between
    "not provided" and "explicitly set to null".
    """

    custom_title: str | None = None
    # Use __unset__ sentinel to detect if folder_id was explicitly provided
    folder_id: str | None = "__unset__"
    # Feed URL update (updates the underlying feed)
    feed_url: HttpUrl | None = None


class BatchDeleteSubscriptionsRequest(BaseModel):
    """Batch delete subscriptions request."""

    subscription_ids: list[str]


class BatchDeleteSubscriptionsResponse(BaseModel):
    """Batch delete subscriptions response."""

    deleted_count: int
    failed_count: int


class SubscriptionListResponse(BaseModel):
    """Paginated subscription list response."""

    items: list[SubscriptionResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class SubscriptionSyncResponse(BaseModel):
    """Sync response for all subscriptions with ETag."""

    items: list[SubscriptionResponse]
    etag: str
