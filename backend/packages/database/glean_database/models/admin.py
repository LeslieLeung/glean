"""
Admin model definitions.

This module defines models for administrative users and system configuration.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class AdminRole(str, Enum):
    """Administrator role enumeration."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"


class AdminUser(Base, TimestampMixin):
    """
    Administrator account model.

    Separate from regular users for enhanced security.

    Attributes:
        id: Unique admin identifier (UUID).
        username: Admin username (unique).
        password_hash: Hashed password.
        role: Administrator role level.
        is_active: Account active status.
        last_login_at: Most recent login timestamp.
    """

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        String(20), default=AdminRole.ADMIN, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SystemConfig(Base, TimestampMixin):
    """
    System configuration key-value store.

    Stores runtime configuration that can be modified
    without redeploying the application.

    Attributes:
        key: Configuration key (primary key).
        value: Configuration value.
        description: Human-readable description.
    """

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
