"""
Admin schemas.

Pydantic models for admin API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminLoginRequest(BaseModel):
    """Admin login request schema."""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    """Admin login response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    admin: "AdminUserResponse"


class AdminUserResponse(BaseModel):
    """Admin user response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserListItem(BaseModel):
    """User list item schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str | None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserListResponse(BaseModel):
    """User list response schema."""

    items: list[UserListItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class ToggleUserStatusRequest(BaseModel):
    """Toggle user status request schema."""

    is_active: bool


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics response schema."""

    total_users: int
    active_users: int
    total_feeds: int
    total_entries: int
    total_subscriptions: int
    new_users_today: int
    new_entries_today: int


# M2: Admin feed management schemas
class AdminFeedListItem(BaseModel):
    """Admin feed list item schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    title: str
    status: str
    subscriber_count: int = 0
    last_fetched_at: datetime | None
    error_count: int = 0
    fetch_error_message: str | None = None
    created_at: datetime


class AdminFeedListResponse(BaseModel):
    """Admin feed list response schema."""

    items: list[AdminFeedListItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class AdminFeedDetailResponse(AdminFeedListItem):
    """Admin feed detail response schema."""

    description: str | None
    icon_url: str | None
    last_error_message: str | None


class AdminFeedUpdateRequest(BaseModel):
    """Admin feed update request schema."""

    url: str | None = None
    title: str | None = None
    status: str | None = None


class AdminBatchFeedRequest(BaseModel):
    """Admin batch feed operation request schema."""

    action: str = Field(..., pattern="^(enable|disable|delete)$")
    feed_ids: list[str]


# M2: Admin entry management schemas
class AdminEntryListItem(BaseModel):
    """Admin entry list item schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    feed_id: str
    feed_title: str = ""
    url: str
    title: str
    author: str | None
    published_at: datetime | None
    created_at: datetime


class AdminEntryListResponse(BaseModel):
    """Admin entry list response schema."""

    items: list[AdminEntryListItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class AdminEntryDetailResponse(AdminEntryListItem):
    """Admin entry detail response schema."""

    content: str | None
    summary: str | None


class AdminBatchEntryRequest(BaseModel):
    """Admin batch entry operation request schema."""

    action: str = Field(..., pattern="^(delete)$")
    entry_ids: list[str]


# System settings: embedding configuration
class EmbeddingRateLimit(BaseModel):
    """Global and per-provider rate limit (rpm)."""

    default: int
    providers: dict[str, int] = Field(default_factory=dict)


class EmbeddingConfigPayload(BaseModel):
    """Embedding configuration payload stored in system settings."""

    provider: str
    model: str
    dimension: int
    rate_limit: EmbeddingRateLimit
    api_key: str | None = None
    base_url: str | None = None
    version: str | None = None
    updated_at: datetime | None = None


class EmbeddingConfigResponse(EmbeddingConfigPayload):
    """Response schema for embedding config."""

    pass


class EmbeddingRebuildStatus(BaseModel):
    """Embedding rebuild progress."""

    total: int
    done: int
    failed: int
