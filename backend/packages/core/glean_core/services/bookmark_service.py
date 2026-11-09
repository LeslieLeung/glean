"""
Bookmark service.

Handles bookmark CRUD operations and folder/tag associations.
"""

import json
from math import ceil
from typing import Any, cast

from arq.connections import ArqRedis
from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from glean_core import RedisKeys, get_logger
from glean_core.schemas.bookmark import (
    BookmarkCreate,
    BookmarkFolderSimple,
    BookmarkListResponse,
    BookmarkResponse,
    BookmarkTagSimple,
    BookmarkUpdate,
)
from glean_database.models import (
    Bookmark,
    BookmarkFolder,
    BookmarkTag,
    Entry,
    Feed,
    Folder,
    Tag,
    User,
)
from glean_rss import strip_html_tags

from .preference_dirty_service import mark_preferences_dirty

logger = get_logger(__name__)


class BookmarkService:
    """Bookmark management service."""

    def __init__(self, session: AsyncSession, redis_pool: ArqRedis | None = None):
        """
        Initialize bookmark service.

        Args:
            session: Database session.
            redis_pool: Optional Redis connection pool for task queue.
        """
        self.session = session
        self.redis_pool = redis_pool

    async def get_bookmarks(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
        folder_id: str | None = None,
        tag_ids: list[str] | None = None,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
        unfiled: bool = False,
        source_type: str | None = None,
    ) -> BookmarkListResponse:
        """
        Get bookmarks for a user with filtering and pagination.

        Args:
            user_id: User identifier.
            page: Page number (1-based).
            per_page: Items per page.
            folder_id: Filter by folder.
            tag_ids: Filter by tags (intersection).
            search: Search title, summary, URL and source name.
            sort: Sort field (created_at or title).
            order: Sort order (asc or desc).

        Returns:
            Paginated bookmark list response.
        """
        # Base query
        base_query = select(Bookmark).where(Bookmark.user_id == user_id)

        # Filter by folder
        if unfiled:
            base_query = base_query.where(~Bookmark.bookmark_folders.any())
        if source_type:
            base_query = base_query.where(Bookmark.source_type == source_type)
        if folder_id:
            descendants = (
                select(Folder.id)
                .where(Folder.id == folder_id, Folder.user_id == user_id)
                .cte(recursive=True)
            )
            descendants = descendants.union_all(
                select(Folder.id)
                .join(descendants, Folder.parent_id == descendants.c.id)
                .where(Folder.user_id == user_id)
            )
            base_query = base_query.where(
                Bookmark.id.in_(
                    select(BookmarkFolder.bookmark_id).where(
                        BookmarkFolder.folder_id.in_(select(descendants.c.id))
                    )
                )
            )

        # Filter by tags (intersection)
        if tag_ids:
            for tag_id in tag_ids:
                subquery = (
                    select(BookmarkTag.bookmark_id).where(BookmarkTag.tag_id == tag_id).subquery()
                )
                base_query = base_query.where(Bookmark.id.in_(select(subquery)))

        # Search
        if search:
            term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            base_query = base_query.where(
                or_(
                    *(
                        column.ilike(term, escape="\\")
                        for column in (
                            Bookmark.title,
                            Bookmark.excerpt,
                            Bookmark.url,
                            Bookmark.source_name,
                        )
                    )
                )
            )

        # Count total
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        # Sorting
        order_column = getattr(Bookmark, sort, Bookmark.created_at)
        order_column = order_column.desc() if order == "desc" else order_column.asc()

        # Pagination
        query = (
            base_query.options(
                selectinload(Bookmark.bookmark_folders).selectinload(BookmarkFolder.folder),
                selectinload(Bookmark.bookmark_tags).selectinload(BookmarkTag.tag),
            )
            .order_by(order_column, Bookmark.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )

        result = await self.session.execute(query)
        bookmarks = result.scalars().unique().all()

        # Build response
        items: list[BookmarkResponse] = []
        for bookmark in bookmarks:
            folders = [
                BookmarkFolderSimple(id=bf.folder.id, name=bf.folder.name)
                for bf in bookmark.bookmark_folders
            ]
            tags = [
                BookmarkTagSimple(id=bt.tag.id, name=bt.tag.name, color=bt.tag.color)
                for bt in bookmark.bookmark_tags
            ]
            items.append(
                BookmarkResponse(
                    id=bookmark.id,
                    user_id=bookmark.user_id,
                    entry_id=bookmark.entry_id,
                    url=bookmark.url,
                    title=bookmark.title,
                    excerpt=bookmark.excerpt,
                    content=bookmark.content,
                    snapshot_status=bookmark.snapshot_status,
                    source_type=bookmark.source_type,
                    source_name=bookmark.source_name,
                    folders=folders,
                    tags=tags,
                    created_at=bookmark.created_at,
                    updated_at=bookmark.updated_at,
                )
            )

        return BookmarkListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=ceil(total / per_page) if total > 0 else 1,
        )

    async def get_bookmark(self, bookmark_id: str, user_id: str) -> BookmarkResponse:
        """
        Get a specific bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            user_id: User identifier for authorization.

        Returns:
            Bookmark response.

        Raises:
            ValueError: If bookmark not found or unauthorized.
        """
        stmt = (
            select(Bookmark)
            .where(Bookmark.id == bookmark_id, Bookmark.user_id == user_id)
            .options(
                selectinload(Bookmark.bookmark_folders).selectinload(BookmarkFolder.folder),
                selectinload(Bookmark.bookmark_tags).selectinload(BookmarkTag.tag),
            )
        )
        result = await self.session.execute(stmt)
        bookmark = result.scalar_one_or_none()

        if not bookmark:
            raise ValueError("Bookmark not found")

        folders = [
            BookmarkFolderSimple(id=bf.folder.id, name=bf.folder.name)
            for bf in bookmark.bookmark_folders
        ]
        tags = [
            BookmarkTagSimple(id=bt.tag.id, name=bt.tag.name, color=bt.tag.color)
            for bt in bookmark.bookmark_tags
        ]

        return BookmarkResponse(
            id=bookmark.id,
            user_id=bookmark.user_id,
            entry_id=bookmark.entry_id,
            url=bookmark.url,
            title=bookmark.title,
            excerpt=bookmark.excerpt,
            content=bookmark.content,
            snapshot_status=bookmark.snapshot_status,
            source_type=bookmark.source_type,
            source_name=bookmark.source_name,
            folders=folders,
            tags=tags,
            created_at=bookmark.created_at,
            updated_at=bookmark.updated_at,
        )

    async def create_bookmark(
        self, user_id: str, data: BookmarkCreate
    ) -> tuple[BookmarkResponse, bool]:
        """
        Create a new bookmark.

        Args:
            user_id: User identifier.
            data: Bookmark creation data.

        Returns:
            Tuple of (created bookmark response, needs_metadata_fetch flag).
            needs_metadata_fetch is True when a saved body is not yet available.

        Raises:
            ValueError: If entry not found or validation fails.
        """
        # Serialize creates per owner, including cross-source duplicates.
        await self.session.execute(select(User.id).where(User.id == user_id).with_for_update())
        entry_id = data.entry_id
        entry = None
        url = data.url
        source_name = None
        if data.entry_id:
            entry = await self.session.get(Entry, data.entry_id)
            if not entry:
                raise ValueError("Entry not found")
            url = entry.url
            source_name = await self.session.scalar(
                select(Feed.title).where(Feed.id == entry.feed_id)
            )
        conditions: list[ColumnElement[bool]] = []
        if data.entry_id:
            conditions.append(Bookmark.entry_id == data.entry_id)
        if url:
            # Exact addresses only: query strings and fragments can identify distinct resources.
            conditions.append(Bookmark.url == url)
            conditions.append(Bookmark.entry_id.in_(select(Entry.id).where(Entry.url == url)))
        existing = await self.session.scalar(
            select(Bookmark)
            .where(Bookmark.user_id == user_id, or_(*conditions))
            .order_by(Bookmark.created_at)
            .limit(1)
        )
        if existing:
            # Attach an external save to its RSS entry without replacing user metadata.
            if entry and not existing.entry_id:
                existing.entry_id = entry.id
                existing.content = existing.content or entry.content
                await mark_preferences_dirty(self.session, [user_id])
            await self.session.commit()
            if entry:
                await self._queue_preference_sync(user_id)
            result = await self.get_bookmark(existing.id, user_id)
            result.already_exists = True
            return result, False
        needs_metadata_fetch = entry is None or not entry.content
        bookmark = Bookmark(
            user_id=user_id,
            entry_id=data.entry_id,
            url=url,
            title=(data.title or (entry.title if entry else url) or "")[:500],
            excerpt=data.excerpt
            if data.excerpt is not None
            else (
                strip_html_tags(entry.summary or entry.content or "", max_length=200)
                if entry
                else None
            ),
            content=entry.content if entry else None,
            source_type="rss" if entry else "external",
            source_name=source_name,
            title_edited=bool(data.title),
            excerpt_edited=data.excerpt is not None,
            snapshot_status="pending" if needs_metadata_fetch else "done",
        )
        self.session.add(bookmark)
        await self.session.flush()

        # Add folders
        for folder_id in set(data.folder_ids):
            # Verify folder exists and belongs to user
            folder_stmt = select(Folder).where(
                Folder.id == folder_id,
                Folder.user_id == user_id,
                Folder.type == "bookmark",
            )
            folder_result = await self.session.execute(folder_stmt)
            if folder_result.scalar_one_or_none():
                self.session.add(BookmarkFolder(bookmark_id=bookmark.id, folder_id=folder_id))

        # Add tags
        for tag_id in set(data.tag_ids):
            # Verify tag exists and belongs to user
            tag_stmt = select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
            tag_result = await self.session.execute(tag_stmt)
            if tag_result.scalar_one_or_none():
                self.session.add(BookmarkTag(bookmark_id=bookmark.id, tag_id=tag_id))

        if entry_id:
            await mark_preferences_dirty(self.session, [user_id])
        await self.session.commit()

        # Queue an idempotent current-state sync for entry-backed bookmarks.
        if entry_id:
            await self._queue_preference_sync(user_id)

        # Return with associations
        return await self.get_bookmark(bookmark.id, user_id), needs_metadata_fetch

    async def update_bookmark(
        self, bookmark_id: str, user_id: str, data: BookmarkUpdate
    ) -> BookmarkResponse:
        """
        Update a bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            user_id: User identifier for authorization.
            data: Update data.

        Returns:
            Updated bookmark response.

        Raises:
            ValueError: If bookmark not found or unauthorized.
        """
        bookmark = await self._get_bookmark_or_raise(bookmark_id, user_id)

        if data.title is not None:
            bookmark.title = data.title
            bookmark.title_edited = True
        if "excerpt" in data.model_fields_set:
            bookmark.excerpt = data.excerpt
            bookmark.excerpt_edited = True

        await self.session.commit()
        return await self.get_bookmark(bookmark_id, user_id)

    async def delete_bookmark(self, bookmark_id: str, user_id: str) -> None:
        """
        Delete a bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            user_id: User identifier for authorization.

        Raises:
            ValueError: If bookmark not found or unauthorized.
        """
        bookmark = await self._get_bookmark_or_raise(bookmark_id, user_id)
        entry_id = bookmark.entry_id
        if self.redis_pool:
            snapshot = (await self.get_bookmark(bookmark_id, user_id)).model_dump(mode="json")
            snapshot.update(
                title_edited=bookmark.title_edited, excerpt_edited=bookmark.excerpt_edited
            )
            await self.redis_pool.setex(
                f"bookmark:undo:{user_id}:{bookmark_id}", 30, json.dumps(snapshot)
            )
        await self.session.delete(bookmark)
        if entry_id:
            await mark_preferences_dirty(self.session, [user_id])
        await self.session.commit()
        if entry_id:
            await self._queue_preference_sync(user_id)

    async def retry_content(self, bookmark_id: str, user_id: str) -> BookmarkResponse:
        bookmark = await self._get_bookmark_or_raise(bookmark_id, user_id)
        if not bookmark.url:
            raise ValueError("Bookmark has no URL")
        bookmark.snapshot_status = "pending"
        await self.session.commit()
        await self.queue_content(bookmark_id)
        return await self.get_bookmark(bookmark_id, user_id)

    async def queue_content(self, bookmark_id: str) -> None:
        try:
            if not self.redis_pool:
                raise RuntimeError("Queue unavailable")
            await self.redis_pool.enqueue_job("fetch_bookmark_metadata_task", bookmark_id)
        except Exception:
            bookmark = await self.session.get(Bookmark, bookmark_id)
            if bookmark:
                bookmark.snapshot_status = "failed"
                await self.session.commit()
            logger.exception("Unable to queue bookmark content")

    async def restore_bookmark(self, bookmark_id: str, user_id: str) -> BookmarkResponse:
        """Restore the exact saved content and associations during the undo window."""
        await self.session.execute(select(User.id).where(User.id == user_id).with_for_update())
        existing = await self.session.get(Bookmark, bookmark_id)
        if existing and existing.user_id == user_id:
            await self.session.commit()
            return await self.get_bookmark(bookmark_id, user_id)
        key = f"bookmark:undo:{user_id}:{bookmark_id}"
        raw = await self.redis_pool.get(key) if self.redis_pool else None
        if not raw:
            raise ValueError("Undo expired")
        saved = json.loads(raw)
        data = BookmarkResponse.model_validate(saved)
        entry_id = (
            data.entry_id
            if data.entry_id and await self.session.get(Entry, data.entry_id)
            else None
        )
        duplicate = await self.session.scalar(
            select(Bookmark)
            .where(
                Bookmark.user_id == user_id,
                or_(
                    Bookmark.url == data.url if data.url else false(),
                    Bookmark.entry_id == entry_id if entry_id else false(),
                ),
            )
            .limit(1)
        )
        if duplicate:
            raise ValueError("This content has already been saved again")
        bookmark = Bookmark(
            id=data.id,
            user_id=user_id,
            entry_id=entry_id,
            url=data.url,
            title=data.title,
            excerpt=data.excerpt,
            content=data.content,
            source_type=data.source_type,
            source_name=data.source_name,
            snapshot_status=data.snapshot_status,
            title_edited=saved.get("title_edited", True),
            excerpt_edited=saved.get("excerpt_edited", True),
            created_at=data.created_at,
            updated_at=data.updated_at,
        )
        self.session.add(bookmark)
        await self.session.flush()
        for folder in data.folders:
            if await self.session.scalar(
                select(Folder.id).where(Folder.id == folder.id, Folder.user_id == user_id)
            ):
                self.session.add(BookmarkFolder(bookmark_id=bookmark_id, folder_id=folder.id))
        for tag in data.tags:
            if await self.session.scalar(
                select(Tag.id).where(Tag.id == tag.id, Tag.user_id == user_id)
            ):
                self.session.add(BookmarkTag(bookmark_id=bookmark_id, tag_id=tag.id))
        if entry_id:
            await mark_preferences_dirty(self.session, [user_id])
        await self.session.commit()
        if self.redis_pool:
            await self.redis_pool.delete(key)
        if entry_id:
            await self._queue_preference_sync(user_id)
        if data.snapshot_status in ("pending", "processing"):
            await self.queue_content(bookmark_id)
        return await self.get_bookmark(bookmark_id, user_id)

    async def _queue_preference_sync(self, user_id: str) -> None:
        """Best-effort enqueue of a current-state preference rebuild."""
        if not self.redis_pool:
            return
        try:
            await cast(Any, self.redis_pool).sadd(
                RedisKeys.PREFERENCE_PENDING_USERS_KEY,
                user_id,
            )
            await self.redis_pool.enqueue_job(
                "rebuild_user_preference",
                user_id=user_id,
            )
        except Exception as error:
            # The bookmark write has already committed and remains the source
            # of truth; a later full rebuild can safely recover this signal.
            logger.warning(f"Failed to queue preference sync: {error}")

    async def add_folder(self, bookmark_id: str, user_id: str, folder_id: str) -> BookmarkResponse:
        """
        Add a folder to a bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            user_id: User identifier for authorization.
            folder_id: Folder identifier.

        Returns:
            Updated bookmark response.

        Raises:
            ValueError: If bookmark/folder not found or unauthorized.
        """
        await self._get_bookmark_or_raise(bookmark_id, user_id)

        # Verify folder exists and belongs to user
        folder_stmt = select(Folder).where(
            Folder.id == folder_id,
            Folder.user_id == user_id,
            Folder.type == "bookmark",
        )
        folder_result = await self.session.execute(folder_stmt)
        if not folder_result.scalar_one_or_none():
            raise ValueError("Folder not found")

        # Check if already exists
        existing_stmt = select(BookmarkFolder).where(
            BookmarkFolder.bookmark_id == bookmark_id,
            BookmarkFolder.folder_id == folder_id,
        )
        existing_result = await self.session.execute(existing_stmt)
        if not existing_result.scalar_one_or_none():
            self.session.add(BookmarkFolder(bookmark_id=bookmark_id, folder_id=folder_id))
            await self.session.commit()

        return await self.get_bookmark(bookmark_id, user_id)

    async def remove_folder(
        self, bookmark_id: str, user_id: str, folder_id: str
    ) -> BookmarkResponse:
        """
        Remove a folder from a bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            user_id: User identifier for authorization.
            folder_id: Folder identifier.

        Returns:
            Updated bookmark response.

        Raises:
            ValueError: If bookmark not found or unauthorized.
        """
        await self._get_bookmark_or_raise(bookmark_id, user_id)

        stmt = select(BookmarkFolder).where(
            BookmarkFolder.bookmark_id == bookmark_id,
            BookmarkFolder.folder_id == folder_id,
        )
        result = await self.session.execute(stmt)
        bf = result.scalar_one_or_none()
        if bf:
            await self.session.delete(bf)
            await self.session.commit()

        return await self.get_bookmark(bookmark_id, user_id)

    async def add_tag(self, bookmark_id: str, user_id: str, tag_id: str) -> BookmarkResponse:
        """
        Add a tag to a bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            user_id: User identifier for authorization.
            tag_id: Tag identifier.

        Returns:
            Updated bookmark response.

        Raises:
            ValueError: If bookmark/tag not found or unauthorized.
        """
        await self._get_bookmark_or_raise(bookmark_id, user_id)

        # Verify tag exists and belongs to user
        tag_stmt = select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        tag_result = await self.session.execute(tag_stmt)
        if not tag_result.scalar_one_or_none():
            raise ValueError("Tag not found")

        # Check if already exists
        existing_stmt = select(BookmarkTag).where(
            BookmarkTag.bookmark_id == bookmark_id,
            BookmarkTag.tag_id == tag_id,
        )
        existing_result = await self.session.execute(existing_stmt)
        if not existing_result.scalar_one_or_none():
            self.session.add(BookmarkTag(bookmark_id=bookmark_id, tag_id=tag_id))
            await self.session.commit()

        return await self.get_bookmark(bookmark_id, user_id)

    async def remove_tag(self, bookmark_id: str, user_id: str, tag_id: str) -> BookmarkResponse:
        """
        Remove a tag from a bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            user_id: User identifier for authorization.
            tag_id: Tag identifier.

        Returns:
            Updated bookmark response.

        Raises:
            ValueError: If bookmark not found or unauthorized.
        """
        await self._get_bookmark_or_raise(bookmark_id, user_id)

        stmt = select(BookmarkTag).where(
            BookmarkTag.bookmark_id == bookmark_id,
            BookmarkTag.tag_id == tag_id,
        )
        result = await self.session.execute(stmt)
        bt = result.scalar_one_or_none()
        if bt:
            await self.session.delete(bt)
            await self.session.commit()

        return await self.get_bookmark(bookmark_id, user_id)

    async def _get_bookmark_or_raise(self, bookmark_id: str, user_id: str) -> Bookmark:
        """Get a bookmark by ID or raise ValueError."""
        stmt = select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == user_id)
        result = await self.session.execute(stmt)
        bookmark = result.scalar_one_or_none()
        if not bookmark:
            raise ValueError("Bookmark not found")
        return bookmark
