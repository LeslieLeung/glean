"""
User schemas.

Request and response models for user-related operations.
"""

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Base user fields."""

    email: EmailStr | None = None  # Email can be None for OAuth users without email scope
    name: str | None = None
    username: str | None = None  # Username (e.g., preferred_username from OIDC)
    phone: str | None = None  # Phone number (e.g., phone_number from OIDC)


class UserResponse(UserBase):
    """User response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    avatar_url: str | None = None
    is_active: bool
    is_verified: bool
    settings: dict[str, Any] | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    """User creation request (for internal use)."""

    email: EmailStr
    name: str
    password: str


class UserUpdate(BaseModel):
    """User update request."""

    name: str | None = Field(None, max_length=100)
    username: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=50)
    avatar_url: str | None = Field(None, max_length=2048)
    settings: dict[str, Any] | None = None

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        cleaned = v.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("avatar_url must use http or https scheme with a valid host")
        return cleaned

    @field_validator("settings")
    @classmethod
    def validate_settings_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        if len(json.dumps(v)) > 32768:
            raise ValueError("settings payload exceeds maximum allowed size")
        return v
