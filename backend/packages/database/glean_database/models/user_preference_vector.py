"""
UserPreferenceVector model definition.

Stores user preference vectors in PostgreSQL pgvector backend.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import BIGINT, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserPreferenceVector(Base):
    """User preference vectors for pgvector backend."""

    __tablename__ = "user_preference_vectors"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    vector_type: Mapped[str] = mapped_column(String(20), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector())  # type: ignore[misc,valid-type]
    sample_count: Mapped[float] = mapped_column(nullable=False)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "vector_type", name="uq_user_vector_type"),)
