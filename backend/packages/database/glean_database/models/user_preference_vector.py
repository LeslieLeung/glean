"""
UserPreferenceVector model definition.

Stores user preference vectors in PostgreSQL pgvector backend.
"""

from sqlalchemy import BIGINT, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - optional dependency during partial installs
    Vector = None  # type: ignore[assignment,misc]

VECTOR_TYPE = Vector() if Vector is not None else JSON


class UserPreferenceVector(Base):
    """User preference vectors for pgvector backend."""

    __tablename__ = "user_preference_vectors"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    vector_type: Mapped[str] = mapped_column(String(20), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR_TYPE)  # type: ignore[misc,valid-type]
    sample_count: Mapped[float] = mapped_column(nullable=False)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "vector_type", name="uq_user_vector_type"),)
