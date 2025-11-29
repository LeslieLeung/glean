"""
Base model classes and mixins.

This module provides the SQLAlchemy declarative base and common mixins
for timestamp tracking and UUID generation.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class for all models."""

    pass


class TimestampMixin:
    """
    Mixin for automatic timestamp tracking.

    Adds created_at and updated_at columns with automatic
    server-side timestamp management.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def generate_uuid() -> str:
    """
    Generate a new UUID string.

    Returns:
        UUID4 string representation.
    """
    return str(uuid4())
