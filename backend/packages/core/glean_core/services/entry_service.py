"""
Entry service.

Handles entry retrieval and user-specific entry state management.
"""

from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas import EntryListResponse, EntryResponse, UpdateEntryStateRequest
from glean_database.models import Entry, Subscription, UserEntry


class EntryService:
    """Entry management service."""

    def __init__(self, session: AsyncSession):
        """
        Initialize entry service.

        Args:
            session: Database session.
        """
        self.session = session

    async def get_entries(
        self,
        user_id: str,
        feed_id: str | None = None,
        is_read: bool | None = None,
        is_liked: bool | None = None,
        read_later: bool | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> EntryListResponse:
        """
        Get entries for a user with filtering and pagination.

        Args:
            user_id: User identifier.
            feed_id: Optional feed filter.
            is_read: Optional read status filter.
            is_liked: Optional liked status filter.
            read_later: Optional read later filter.
            page: Page number (1-indexed).
            per_page: Items per page.

        Returns:
            Paginated entry list response.
        """
        # Get user's subscribed feed IDs
        subscriptions_stmt = select(Subscription.feed_id).where(Subscription.user_id == user_id)
        result = await self.session.execute(subscriptions_stmt)
        feed_ids = [row[0] for row in result.all()]

        if not feed_ids:
            return EntryListResponse(
                items=[], total=0, page=page, per_page=per_page, has_more=False
            )

        # Build query for entries
        stmt = (
            select(Entry, UserEntry)
            .outerjoin(
                UserEntry,
                (Entry.id == UserEntry.entry_id) & (UserEntry.user_id == user_id),
            )
            .where(Entry.feed_id.in_(feed_ids))
        )

        # Apply filters
        if feed_id:
            stmt = stmt.where(Entry.feed_id == feed_id)
        if is_read is not None:
            if is_read:
                stmt = stmt.where(UserEntry.is_read.is_(True))
            else:
                stmt = stmt.where((UserEntry.is_read.is_(False)) | (UserEntry.is_read.is_(None)))
        if is_liked is not None:
            stmt = stmt.where(UserEntry.is_liked == is_liked)
        if read_later is not None:
            stmt = stmt.where(UserEntry.read_later == read_later)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        stmt = stmt.order_by(desc(Entry.published_at)).limit(per_page).offset((page - 1) * per_page)

        result = await self.session.execute(stmt)
        rows = result.all()

        # Build response items
        items: list[EntryResponse] = []
        for entry, user_entry in rows:
            items.append(
                EntryResponse(
                    id=str(entry.id),
                    feed_id=str(entry.feed_id),
                    url=str(entry.url),
                    title=str(entry.title),
                    author=entry.author,
                    content=entry.content,
                    summary=entry.summary,
                    published_at=entry.published_at,
                    created_at=entry.created_at,
                    is_read=bool(user_entry.is_read) if user_entry else False,
                    is_liked=user_entry.is_liked if user_entry else None,
                    read_later=bool(user_entry.read_later) if user_entry else False,
                    read_at=user_entry.read_at if user_entry else None,
                )
            )

        has_more = total > page * per_page

        return EntryListResponse(
            items=items, total=total, page=page, per_page=per_page, has_more=has_more
        )

    async def get_entry(self, entry_id: str, user_id: str) -> EntryResponse:
        """
        Get a specific entry.

        Args:
            entry_id: Entry identifier.
            user_id: User identifier.

        Returns:
            Entry response.

        Raises:
            ValueError: If entry not found or user not subscribed.
        """
        stmt = (
            select(Entry, UserEntry)
            .outerjoin(
                UserEntry,
                (Entry.id == UserEntry.entry_id) & (UserEntry.user_id == user_id),
            )
            .where(Entry.id == entry_id)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()

        if not row:
            raise ValueError("Entry not found")

        entry, user_entry = row

        # Verify user is subscribed to this feed
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user_id, Subscription.feed_id == entry.feed_id
        )
        sub_result = await self.session.execute(sub_stmt)
        if not sub_result.scalar_one_or_none():
            raise ValueError("Not subscribed to this feed")

        return EntryResponse(
            id=str(entry.id),
            feed_id=str(entry.feed_id),
            url=str(entry.url),
            title=str(entry.title),
            author=entry.author,
            content=entry.content,
            summary=entry.summary,
            published_at=entry.published_at,
            created_at=entry.created_at,
            is_read=bool(user_entry.is_read) if user_entry else False,
            is_liked=user_entry.is_liked if user_entry else None,
            read_later=bool(user_entry.read_later) if user_entry else False,
            read_at=user_entry.read_at if user_entry else None,
        )

    async def update_entry_state(
        self, entry_id: str, user_id: str, update: UpdateEntryStateRequest
    ) -> EntryResponse:
        """
        Update user-specific entry state.

        Args:
            entry_id: Entry identifier.
            user_id: User identifier.
            update: State update data.

        Returns:
            Updated entry response.

        Raises:
            ValueError: If entry not found.
        """
        # Verify entry exists and user has access
        entry_stmt = select(Entry).where(Entry.id == entry_id)
        entry_result = await self.session.execute(entry_stmt)
        entry = entry_result.scalar_one_or_none()

        if not entry:
            raise ValueError("Entry not found")

        # Verify user is subscribed to this feed
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user_id, Subscription.feed_id == entry.feed_id
        )
        sub_result = await self.session.execute(sub_stmt)
        if not sub_result.scalar_one_or_none():
            raise ValueError("Not subscribed to this feed")

        # Get or create UserEntry
        stmt = select(UserEntry).where(UserEntry.entry_id == entry_id, UserEntry.user_id == user_id)
        result = await self.session.execute(stmt)
        user_entry = result.scalar_one_or_none()

        if not user_entry:
            # Create new UserEntry
            user_entry = UserEntry(entry_id=entry_id, user_id=user_id)
            self.session.add(user_entry)

        # Update fields
        # Use model_dump(exclude_unset=True) to only update explicitly set fields
        now = datetime.now(UTC)
        update_data = update.model_dump(exclude_unset=True)

        if "is_read" in update_data and update.is_read is not None:
            user_entry.is_read = update.is_read
            if update.is_read:
                user_entry.read_at = now

        if "is_liked" in update_data:
            # is_liked can be True, False, or None
            user_entry.is_liked = update.is_liked
            # Update liked_at timestamp when like/dislike is set (not when cleared to null)
            if update.is_liked is not None:
                user_entry.liked_at = now

        if "read_later" in update_data and update.read_later is not None:
            user_entry.read_later = update.read_later

        await self.session.commit()

        # Return updated entry
        return await self.get_entry(entry_id, user_id)

    async def mark_all_read(self, user_id: str, feed_id: str | None = None) -> None:
        """
        Mark all entries as read.

        Args:
            user_id: User identifier.
            feed_id: Optional feed filter.
        """
        # Get user's subscribed feed IDs
        subscriptions_stmt = select(Subscription.feed_id).where(Subscription.user_id == user_id)
        result = await self.session.execute(subscriptions_stmt)
        feed_ids = [row[0] for row in result.all()]

        if not feed_ids:
            return

        # Get all entries
        entries_stmt = select(Entry.id).where(Entry.feed_id.in_(feed_ids))
        if feed_id:
            entries_stmt = entries_stmt.where(Entry.feed_id == feed_id)

        result = await self.session.execute(entries_stmt)
        entry_ids = [row[0] for row in result.all()]

        # Update or create UserEntry records
        now = datetime.now(UTC)
        for entry_id in entry_ids:
            stmt = select(UserEntry).where(
                UserEntry.entry_id == entry_id, UserEntry.user_id == user_id
            )
            result = await self.session.execute(stmt)
            user_entry = result.scalar_one_or_none()

            if user_entry:
                user_entry.is_read = True
                user_entry.read_at = now
            else:
                user_entry = UserEntry(
                    entry_id=entry_id, user_id=user_id, is_read=True, read_at=now
                )
                self.session.add(user_entry)

        await self.session.commit()
