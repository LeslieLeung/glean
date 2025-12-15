"""
UserPreferenceStats model definition.

This module defines the UserPreferenceStats model for storing user preference statistics.
"""

from typing import Any

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class UserPreferenceStats(Base, TimestampMixin):
    """
    User preference statistics (non-vector data).

    Stores aggregated statistics about user preferences for fast access.
    Actual preference vectors are stored in Milvus.

    Attributes:
        id: Unique stats identifier (UUID).
        user_id: User reference (unique).
        positive_count: Number of likes (weighted).
        negative_count: Number of dislikes (weighted).
        source_affinity: Per-feed affinity scores (JSON).
        author_affinity: Per-author affinity scores (JSON).
    """

    __tablename__ = "user_preference_stats"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Foreign key
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Aggregated counts
    positive_count: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    negative_count: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Affinity mappings (JSON)
    # Format: {"feed_uuid": {"positive": 5, "negative": 1}}
    source_affinity: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    author_affinity: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    user = relationship("User", back_populates="preference_stats")
