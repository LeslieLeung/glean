"""
Bookmark service.

Handles bookmark CRUD operations and folder/tag associations.
"""

from math import ceil

from arq.connections import ArqRedis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from glean_core import get_logger
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
    Folder,
    Tag,
)
from glean_rss import strip_html_tags

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
    ) -> BookmarkListResponse:
        """
        Get bookmarks for a user with filtering and pagination.

        Args:
            user_id: User identifier.
            page: Page number (1-based).
            per_page: Items per page.
            folder_id: Filter by folder.
            tag_ids: Filter by tags (intersection).
            search: Search in title.
            sort: Sort field (created_at or title).
            order: Sort order (asc or desc).

        Returns:
            Paginated bookmark list response.
        """
        # Base query
        base_query = select(Bookmark).where(Bookmark.user_id == user_id)

        # Filter by folder
        if folder_id:
            base_query = base_query.join(BookmarkFolder).where(
                BookmarkFolder.folder_id == folder_id
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
            base_query = base_query.where(Bookmark.title.ilike(f"%{search}%"))

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
            .order_by(order_column)
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
            needs_metadata_fetch is True when title/excerpt need to be fetched
            asynchronously for URL bookmarks.

        Raises:
            ValueError: If entry not found or validation fails.
        """
        title = data.title
        excerpt = data.excerpt
        entry_id = data.entry_id
        url = data.url
        needs_metadata_fetch = False

        # If bookmarking an entry, get its details
        if entry_id:
            # Check if bookmark already exists for this entry
            existing_stmt = select(Bookmark).where(
                Bookmark.user_id == user_id,
                Bookmark.entry_id == entry_id,
            )
            existing_result = await self.session.execute(existing_stmt)
            existing_bookmark = existing_result.scalar_one_or_none()
            if existing_bookmark:
                # Return existing bookmark instead of creating duplicate
                return await self.get_bookmark(existing_bookmark.id, user_id), False

            stmt = select(Entry).where(Entry.id == entry_id)
            result = await self.session.execute(stmt)
            entry = result.scalar_one_or_none()
            if not entry:
                raise ValueError("Entry not found")
            title = title or entry.title
            # Use same logic as article list: content first, then summary
            if not excerpt:
                source_content = entry.content or entry.summary
                if source_content:
                    excerpt = strip_html_tags(source_content, max_length=200)
        elif url:
            # URL bookmark without title - need to fetch metadata asynchronously
            if not title:
                # Use URL as temporary title until metadata is fetched
                title = url
                needs_metadata_fetch = True
            elif not excerpt:
                # Have title but no excerpt - still fetch metadata for excerpt
                needs_metadata_fetch = True

        # Create bookmark
        bookmark = Bookmark(
            user_id=user_id,
            entry_id=entry_id,
            url=url,
            title=title,
            excerpt=excerpt,
            snapshot_status="pending",
        )
        self.session.add(bookmark)
        await self.session.flush()

        # Add folders
        for folder_id in data.folder_ids:
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
        for tag_id in data.tag_ids:
            # Verify tag exists and belongs to user
            tag_stmt = select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
            tag_result = await self.session.execute(tag_stmt)
            if tag_result.scalar_one_or_none():
                self.session.add(BookmarkTag(bookmark_id=bookmark.id, tag_id=tag_id))

        await self.session.commit()

        # Queue preference update task if this is an entry bookmark (M3)
        if entry_id and self.redis_pool:
            try:
                # Debounce: Check if we recently queued bookmark signal for this entry
                debounce_key = f"pref_update_debounce:{user_id}:{entry_id}:bookmark"
                debounce_ttl = 30  # 30 seconds debounce

                # Try to set the key only if it doesn't exist (NX)
                was_set = await self.redis_pool.set(
                    debounce_key,
                    "1",
                    ex=debounce_ttl,
                    nx=True,  # SET if not exists
                )

                # Only queue if key was newly set (not debounced)
                if was_set:
                    await self.redis_pool.enqueue_job(
                        "update_user_preference",
                        user_id=user_id,
                        entry_id=entry_id,
                        signal_type="bookmark",
                    )
                    logger.info(
                        f"Queued preference update: user={user_id[:8]}... "
                        f"entry={entry_id[:8]}... signal=bookmark"
                    )
                else:
                    logger.debug(
                        f"Preference update debounced: user={user_id[:8]}... "
                        f"entry={entry_id[:8]}... signal=bookmark"
                    )
            except Exception as e:
                # Don't fail the request if task queueing fails
                logger.warning(f"Failed to queue preference update: {e}")
                pass

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
        if data.excerpt is not None:
            bookmark.excerpt = data.excerpt

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
        await self.session.delete(bookmark)
        await self.session.commit()

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
