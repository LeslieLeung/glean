"""
User model definition.

This module defines the User model for storing user account information.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class User(Base, TimestampMixin):
    """
    User account model.

    Stores authentication credentials and profile information.

    Attributes:
        id: Unique user identifier (UUID).
        email: User's email address (unique, indexed).
        password_hash: Hashed password for authentication.
        name: Optional display name.
        avatar_url: Optional URL to avatar image.
        is_active: Account active status.
        is_verified: Email verification status.
        last_login_at: Timestamp of most recent login.
        settings: User preferences and settings (JSONB).
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Authentication
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Profile
    name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Settings (JSONB for flexible user preferences)
    settings: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Relationships
    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    user_entries = relationship("UserEntry", back_populates="user", cascade="all, delete-orphan")
    folders = relationship("Folder", back_populates="user", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="user", cascade="all, delete-orphan")
    bookmarks = relationship("Bookmark", back_populates="user", cascade="all, delete-orphan")
    preference_stats = relationship(
        "UserPreferenceStats", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
