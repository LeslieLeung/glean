"""User-owned notes and annotations. Parent locks serialize edits and deletion."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.bookmark import (
    AnnotationCreate,
    AnnotationResponse,
    AnnotationUpdate,
    BookmarkNoteResponse,
    BookmarkNoteUpdate,
)
from glean_database.models import Bookmark, BookmarkAnnotation, BookmarkNote


class RevisionConflictError(ValueError):
    """The client edited a stale revision."""


class BookmarkKnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _owner(self, bookmark_id: str, user_id: str, lock: bool = False) -> Bookmark:
        query = select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == user_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        bookmark = await self.session.scalar(query)
        if bookmark is None:
            raise ValueError("Bookmark not found")
        return bookmark

    async def get_note(self, bookmark_id: str, user_id: str) -> BookmarkNoteResponse:
        await self._owner(bookmark_id, user_id)
        note = await self.session.get(BookmarkNote, bookmark_id)
        return BookmarkNoteResponse.model_validate(note) if note else BookmarkNoteResponse()

    async def save_note(
        self, bookmark_id: str, user_id: str, data: BookmarkNoteUpdate
    ) -> BookmarkNoteResponse:
        await self._owner(bookmark_id, user_id, lock=True)
        note = await self.session.get(BookmarkNote, bookmark_id, populate_existing=True)
        if data.revision != (note.revision if note else 0):
            raise RevisionConflictError("Note changed in another window")
        if note is None:
            note = BookmarkNote(bookmark_id=bookmark_id, body=data.body, revision=1)
            self.session.add(note)
        else:
            note.body = data.body
            note.revision += 1
        await self.session.commit()
        await self.session.refresh(note)
        return BookmarkNoteResponse.model_validate(note)

    async def list_annotations(self, bookmark_id: str, user_id: str) -> list[AnnotationResponse]:
        await self._owner(bookmark_id, user_id)
        annotations = await self.session.scalars(
            select(BookmarkAnnotation)
            .where(BookmarkAnnotation.bookmark_id == bookmark_id)
            .order_by(
                BookmarkAnnotation.start, BookmarkAnnotation.created_at, BookmarkAnnotation.id
            )
        )
        return [AnnotationResponse.model_validate(item) for item in annotations]

    async def create_annotation(
        self, bookmark_id: str, user_id: str, data: AnnotationCreate
    ) -> AnnotationResponse:
        bookmark = await self._owner(bookmark_id, user_id, lock=True)
        if not bookmark.content:
            raise ValueError("Saved article content is required for highlighting")
        annotation = BookmarkAnnotation(bookmark_id=bookmark_id, **data.model_dump())
        self.session.add(annotation)
        await self.session.commit()
        await self.session.refresh(annotation)
        return AnnotationResponse.model_validate(annotation)

    async def update_annotation(
        self, bookmark_id: str, user_id: str, annotation_id: str, data: AnnotationUpdate
    ) -> AnnotationResponse:
        annotation = await self._annotation(bookmark_id, user_id, annotation_id, data.revision)
        annotation.body = data.body
        annotation.color = data.color
        annotation.revision += 1
        await self.session.commit()
        await self.session.refresh(annotation)
        return AnnotationResponse.model_validate(annotation)

    async def delete_annotation(
        self, bookmark_id: str, user_id: str, annotation_id: str, revision: int
    ) -> None:
        annotation = await self._annotation(bookmark_id, user_id, annotation_id, revision)
        await self.session.delete(annotation)
        await self.session.commit()

    async def _annotation(
        self, bookmark_id: str, user_id: str, annotation_id: str, revision: int
    ) -> BookmarkAnnotation:
        await self._owner(bookmark_id, user_id, lock=True)
        annotation = await self.session.scalar(
            select(BookmarkAnnotation)
            .where(
                BookmarkAnnotation.id == annotation_id,
                BookmarkAnnotation.bookmark_id == bookmark_id,
            )
            .execution_options(populate_existing=True)
        )
        if annotation is None:
            raise ValueError("Annotation not found")
        if annotation.revision != revision:
            raise RevisionConflictError("Annotation changed in another window")
        return annotation
