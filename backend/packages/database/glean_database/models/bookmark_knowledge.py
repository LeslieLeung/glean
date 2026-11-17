"""User-authored bookmark notes and anchored annotations."""

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class BookmarkNote(Base, TimestampMixin):
    __tablename__ = "bookmark_notes"

    bookmark_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        Index(
            "ix_bookmark_notes_body",
            "body",
            postgresql_using="gin",
            postgresql_ops={"body": "gin_trgm_ops"},
        ),
    )


class BookmarkAnnotation(Base, TimestampMixin):
    __tablename__ = "bookmark_annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    bookmark_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookmarks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exact: Mapped[str] = mapped_column(Text, nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suffix: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    anchor_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="yellow")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    __table_args__ = (
        CheckConstraint('"end" > start AND start >= 0', name="ck_annotation_position"),
        CheckConstraint("color IN ('yellow', 'green', 'blue', 'pink')", name="ck_annotation_color"),
        Index(
            "ix_bookmark_annotations_search_text",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )


@event.listens_for(BookmarkAnnotation, "before_insert")
@event.listens_for(BookmarkAnnotation, "before_update")
def update_annotation_search(_mapper: Any, _connection: Any, target: BookmarkAnnotation) -> None:
    target.search_text = target.exact + "\n" + (target.body or "")
