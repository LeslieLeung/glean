"""
Bookmark schemas.

Pydantic models for bookmark-related API request/response handling.
"""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BookmarkBase(BaseModel):
    """Base bookmark schema with common fields."""

    title: str = Field(..., min_length=1, max_length=500)
    excerpt: str | None = None


class BookmarkCreate(BaseModel):
    """Schema for creating a new bookmark."""

    entry_id: str | None = None
    url: str | None = Field(None, max_length=2048)
    title: str | None = Field(None, max_length=500)
    excerpt: str | None = None
    folder_ids: list[str] = []
    tag_ids: list[str] = []

    @model_validator(mode="after")
    def validate_source(self) -> "BookmarkCreate":
        """Validate that either entry_id or url is provided."""
        if not self.entry_id and not self.url:
            raise ValueError("Either entry_id or url must be provided")
        if self.url:
            self.url = self.url.strip()
            parsed = urlsplit(self.url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("A valid HTTP(S) URL is required")
        # Title is optional for URL bookmarks - will be fetched asynchronously
        return self


class BookmarkUpdate(BaseModel):
    """Schema for updating a bookmark."""

    title: str | None = Field(None, min_length=1, max_length=500)
    excerpt: str | None = None


class BookmarkFolderSimple(BaseModel):
    """Simple folder info for bookmark response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class BookmarkTagSimple(BaseModel):
    """Simple tag info for bookmark response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color: str | None = None


class BookmarkSearchMatch(BaseModel):
    field: str
    snippet: str


class BookmarkResponse(BaseModel):
    """Response schema for a single bookmark."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    entry_id: str | None
    url: str | None
    title: str
    excerpt: str | None
    content: str | None  # Full article content (HTML) for in-app reading
    source_type: str = "external"
    source_name: str | None = None
    search_matches: list[BookmarkSearchMatch] = []
    already_exists: bool = False
    snapshot_status: str
    folders: list[BookmarkFolderSimple] = []
    tags: list[BookmarkTagSimple] = []
    created_at: datetime
    updated_at: datetime


class BookmarkListResponse(BaseModel):
    """Response schema for paginated bookmark list."""

    items: list[BookmarkResponse]
    total: int
    page: int
    per_page: int
    pages: int


class BookmarkFolderRequest(BaseModel):
    """Schema for adding a folder to a bookmark."""

    folder_id: str


class BookmarkTagRequest(BaseModel):
    """Schema for adding a tag to a bookmark."""

    tag_id: str


class BookmarkNoteUpdate(BaseModel):
    body: str = Field(max_length=100_000)
    revision: int = Field(ge=0)


class BookmarkNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    body: str = ""
    revision: int = 0
    updated_at: datetime | None = None


class AnnotationCreate(BaseModel):
    exact: str = Field(min_length=1, max_length=20_000)
    prefix: str = Field(default="", max_length=200)
    suffix: str = Field(default="", max_length=200)
    start: int = Field(ge=0, le=50_000_000)
    end: int = Field(ge=1, le=50_000_000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    anchor_version: Literal[1] = 1
    body: str = Field(default="", max_length=20_000)
    color: Literal["yellow", "green", "blue", "pink"] = "yellow"

    @model_validator(mode="after")
    def validate_position(self) -> "AnnotationCreate":
        if self.end - self.start != len(self.exact):
            raise ValueError("Position must match the selected Unicode code points")
        return self


class AnnotationUpdate(BaseModel):
    body: str = Field(max_length=20_000)
    color: Literal["yellow", "green", "blue", "pink"] = "yellow"
    revision: int = Field(ge=1)


class AnnotationResponse(AnnotationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision: int
    created_at: datetime
    updated_at: datetime
