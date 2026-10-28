"""
User model definition.

This module defines the User model for storing user account information.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, String
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
        password_hash: Hashed password for authentication (nullable for OAuth users).
        primary_auth_provider: Primary authentication provider (local, oidc, etc.).
        provider_user_id: User ID from authentication provider.
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
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # OAuth users don't need passwords
    primary_auth_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Primary authentication provider (local, oidc, etc.)"
    )
    provider_user_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="User ID from authentication provider"
    )

    # Profile
    name: Mapped[str | None] = mapped_column(String(100))
    username: Mapped[str | None] = mapped_column(
        String(100), comment="Username (e.g., preferred_username from OIDC)"
    )
    phone: Mapped[str | None] = mapped_column(
        String(50), comment="Phone number (e.g., phone_number from OIDC)"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Settings (JSONB for flexible user preferences)
    settings: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Durable preference outbox. Signal-producing transactions increment the
    # revision; a successful history rebuild advances the synced revision.
    # Redis remains an acceleration path, while maintenance can recover every
    # committed signal after a queue outage or process crash.
    preference_revision: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
        nullable=False,
    )
    preference_synced_revision: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
        nullable=False,
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
    api_tokens = relationship("APIToken", back_populates="user", cascade="all, delete-orphan")
    auth_providers = relationship(
        "UserAuthProvider", back_populates="user", cascade="all, delete-orphan"
    )
