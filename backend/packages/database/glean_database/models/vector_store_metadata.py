"""
VectorStoreMetadata model definition.

Stores backend metadata like active model signature for vector tables.
"""

from sqlalchemy import BIGINT, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VectorStoreMetadata(Base):
    """Metadata table for vector backend compatibility checks."""

    __tablename__ = "vector_store_metadata"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    model_signature: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False)
