"""
Entry translation model definition.

This module defines the EntryTranslation model for storing
translated versions of feed entries.
"""

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class EntryTranslation(Base, TimestampMixin):
    """
    Translated entry content.

    Stores translated title and content for a given entry and target language.
    Translations are global (not per-user) so all users benefit from the cache.

    Attributes:
        id: Unique translation identifier (UUID).
        entry_id: Parent entry reference.
        target_language: Target language code (e.g. "zh-CN", "en").
        translated_title: Translated entry title.
        translated_content: Translated entry content (HTML).
        status: Translation status (pending/processing/done/failed).
        error: Error message if translation failed.
    """

    __tablename__ = "entry_translations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_language: Mapped[str] = mapped_column(String(10), nullable=False)
    translated_title: Mapped[str | None] = mapped_column(String(1000))
    translated_content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    paragraph_translations: Mapped[dict[str, str] | None] = mapped_column(JSONB)

    # Relationships
    entry = relationship("Entry", backref="translations")

    # Constraints
    __table_args__ = (
        UniqueConstraint("entry_id", "target_language", name="uq_entry_translation_lang"),
    )
