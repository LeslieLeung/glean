"""
Entry service.

Handles entry retrieval and user-specific entry state management.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from arq.connections import ArqRedis
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas import EntryListResponse, EntryResponse, UpdateEntryStateRequest
from glean_database.models import (
    Bookmark,
    Entry,
    Feed,
    Folder,
    Subscription,
    User,
    UserEntry,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from glean_core.services.simple_score_service import SimpleScoreService
    from glean_vector.services.score_service import ScoreService

    # Union type for score service
    ScoreServiceType = ScoreService | SimpleScoreService


class EntryService:
    """Entry management service."""

    def __init__(self, session: AsyncSession, redis_pool: ArqRedis | None = None):
        """
        Initialize entry service.

        Args:
            session: Database session.
            redis_pool: Optional Redis connection pool for task queue.
        """
        self.session = session
        self.redis_pool = redis_pool

    async def _get_folder_tree_ids(self, folder_id: str, user_id: str) -> list[str]:
        """
        Get all folder IDs in a folder tree (including the folder itself and all descendants).

        Args:
            folder_id: Root folder identifier.
            user_id: User identifier for authorization.

        Returns:
            List of folder IDs.
        """
        result_ids = [folder_id]

        # Find all child folders recursively
        async def get_children(parent_id: str) -> list[str]:
            stmt = select(Folder.id).where(
                Folder.parent_id == parent_id,
                Folder.user_id == user_id,
                Folder.type == "feed",
            )
            result = await self.session.execute(stmt)
            child_ids = [str(row[0]) for row in result.all()]

            all_ids = child_ids.copy()
            for child_id in child_ids:
                all_ids.extend(await get_children(child_id))
            return all_ids

        result_ids.extend(await get_children(folder_id))
        return result_ids

    async def get_entries(
        self,
        user_id: str,
        feed_id: str | None = None,
        folder_id: str | None = None,
        is_read: bool | None = None,
        is_liked: bool | None = None,
        read_later: bool | None = None,
        page: int = 1,
        per_page: int = 20,
        view: str = "timeline",
        score_service: "ScoreServiceType | None" = None,
    ) -> EntryListResponse:
        """
        Get entries for a user with filtering and pagination.

        Args:
            user_id: User identifier.
            feed_id: Optional feed filter.
            folder_id: Optional folder filter (gets entries from all feeds in folder).
            is_read: Optional read status filter (None = all, True = read only, False = unread only).
            is_liked: Optional liked status filter.
            read_later: Optional read later filter.
            page: Page number (1-indexed).
            per_page: Items per page.
            view: View mode ("timeline" or "smart").
            score_service: Score service for real-time scoring (required for smart view).

        Returns:
            Paginated entry list response.
        """

        # Get user's subscribed feed IDs, optionally filtered by folder
        subscriptions_stmt = select(Subscription.feed_id).where(Subscription.user_id == user_id)

        # If folder_id is provided, get feeds in that folder (including nested folders)
        if folder_id:
            # Get all folder IDs (the folder itself and all its descendants)
            folder_ids = await self._get_folder_tree_ids(folder_id, user_id)
            subscriptions_stmt = subscriptions_stmt.where(Subscription.folder_id.in_(folder_ids))

        result = await self.session.execute(subscriptions_stmt)
        feed_ids = [row[0] for row in result.all()]

        if not feed_ids:
            return EntryListResponse(
                items=[], total=0, page=page, per_page=per_page, total_pages=0
            )

        # Subquery to get bookmark_id for entry (limit 1 in case of duplicates)
        bookmark_id_subq = (
            select(Bookmark.id)
            .where(Bookmark.user_id == user_id)
            .where(Bookmark.entry_id == Entry.id)
            .correlate(Entry)
            .limit(1)
            .scalar_subquery()
        )

        # Build query for entries with bookmark info and feed info
        stmt = (
            select(
                Entry,
                UserEntry,
                bookmark_id_subq.label("bookmark_id"),
                Feed.title.label("feed_title"),
                Feed.icon_url.label("feed_icon_url"),
            )
            .join(Feed, Entry.feed_id == Feed.id)
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

        # For smart view, we need to fetch more entries to score and sort
        if view == "smart" and score_service:
            # Fetch more entries for scoring (we'll limit after sorting)
            fetch_limit = min(total, per_page * 5)  # Fetch 5 pages worth for scoring
            stmt_for_scoring = stmt.order_by(desc(Entry.published_at)).limit(
                fetch_limit
            )

            result = await self.session.execute(stmt_for_scoring)
            all_rows = result.all()

            # Extract entries for batch scoring
            entries_for_scoring = [row[0] for row in all_rows]

            # Calculate scores in batch
            # Both ScoreService and SimpleScoreService implement batch_calculate_scores
            # ScoreService returns dict[entry_id, float]
            # SimpleScoreService returns dict[entry_id, dict with 'score' key]
            scores_result = await score_service.batch_calculate_scores(
                user_id, entries_for_scoring
            )

            # Normalize to dict[str, float]
            scores: dict[str, float] = {}
            for entry_id, score_data in scores_result.items():
                if isinstance(score_data, dict):
                    # SimpleScoreService format
                    scores[entry_id] = float(score_data.get("score", 50.0))
                else:
                    # ScoreService format
                    scores[entry_id] = float(score_data)

            # Build items with scores
            items_with_scores: list[tuple[EntryResponse, float]] = []
            for entry, user_entry, bookmark_id, feed_title, feed_icon_url in all_rows:
                score = scores.get(entry.id, 50.0)
                item = EntryResponse(
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
                    read_later_until=(
                        user_entry.read_later_until if user_entry else None
                    ),
                    read_at=user_entry.read_at if user_entry else None,
                    is_bookmarked=bookmark_id is not None,
                    bookmark_id=str(bookmark_id) if bookmark_id else None,
                    preference_score=score,
                    feed_title=feed_title,
                    feed_icon_url=feed_icon_url,
                )
                items_with_scores.append((item, score))

            # Sort by score descending
            items_with_scores.sort(key=lambda x: x[1], reverse=True)

            # Apply pagination
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            items = [item for item, _ in items_with_scores[start_idx:end_idx]]
        else:
            # Timeline view - standard pagination with time ordering
            stmt = (
                stmt.order_by(desc(Entry.published_at))
                .limit(per_page)
                .offset((page - 1) * per_page)
            )

            result = await self.session.execute(stmt)
            rows = result.all()

            # Build response items
            items = []
            for entry, user_entry, bookmark_id, feed_title, feed_icon_url in rows:
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
                        read_later_until=(
                            user_entry.read_later_until if user_entry else None
                        ),
                        read_at=user_entry.read_at if user_entry else None,
                        is_bookmarked=bookmark_id is not None,
                        bookmark_id=str(bookmark_id) if bookmark_id else None,
                        preference_score=None,  # No score for timeline view
                        feed_title=feed_title,
                        feed_icon_url=feed_icon_url,
                    )
                )

        # Calculate total pages
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return EntryListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
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
        # Subquery to get bookmark_id for entry (limit 1 in case of duplicates)
        bookmark_id_subq = (
            select(Bookmark.id)
            .where(Bookmark.user_id == user_id)
            .where(Bookmark.entry_id == Entry.id)
            .correlate(Entry)
            .limit(1)
            .scalar_subquery()
        )

        stmt = (
            select(
                Entry,
                UserEntry,
                bookmark_id_subq.label("bookmark_id"),
                Feed.title.label("feed_title"),
                Feed.icon_url.label("feed_icon_url"),
            )
            .join(Feed, Entry.feed_id == Feed.id)
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

        entry, user_entry, bookmark_id, feed_title, feed_icon_url = row

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
            read_later_until=user_entry.read_later_until if user_entry else None,
            read_at=user_entry.read_at if user_entry else None,
            is_bookmarked=bookmark_id is not None,
            bookmark_id=str(bookmark_id) if bookmark_id else None,
            preference_score=None,  # Scores are calculated real-time in smart view
            feed_title=feed_title,
            feed_icon_url=feed_icon_url,
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

        # Track old is_liked value for preference update
        old_is_liked = user_entry.is_liked if user_entry else None

        if not user_entry:
            # Create new UserEntry
            user_entry = UserEntry(entry_id=entry_id, user_id=user_id)
            self.session.add(user_entry)

        # Update fields
        # Use model_dump(exclude_unset=True) to only update explicitly set fields
        now = datetime.now(UTC)
        update_data = update.model_dump(exclude_unset=True)
        preference_signal_type: str | None = None

        if "is_read" in update_data and update.is_read is not None:
            user_entry.is_read = update.is_read
            if update.is_read:
                user_entry.read_at = now

        if "is_liked" in update_data:
            # is_liked can be True, False, or None
            new_is_liked = update.is_liked

            # Only trigger preference update if value actually changed
            if old_is_liked != new_is_liked and new_is_liked is not None:
                # Map is_liked to signal type
                preference_signal_type = "like" if new_is_liked else "dislike"

            user_entry.is_liked = new_is_liked
            # Update liked_at timestamp when like/dislike is set (not when cleared to null)
            if new_is_liked is not None:
                user_entry.liked_at = now

        if "read_later" in update_data and update.read_later is not None:
            user_entry.read_later = update.read_later
            # Set read_later_until based on read_later_days
            if update.read_later:
                # Use days from request, then user settings, then default to 7
                days = update.read_later_days
                if days is None:
                    # Get user's default from settings
                    user_stmt = select(User).where(User.id == user_id)
                    user_result = await self.session.execute(user_stmt)
                    user = user_result.scalar_one_or_none()
                    if user and user.settings:
                        days = user.settings.get("read_later_days")
                    if days is None:
                        days = 7  # System default
                if days > 0:
                    user_entry.read_later_until = now + timedelta(days=days)
                else:
                    # 0 = never expire
                    user_entry.read_later_until = None
            else:
                # Clearing read_later, also clear read_later_until
                user_entry.read_later_until = None

        await self.session.commit()

        # Queue preference update task if needed (M3)
        if preference_signal_type and self.redis_pool:
            try:
                # Debounce: Check if we recently queued this signal for this entry
                debounce_key = f"pref_update_debounce:{user_id}:{entry_id}:{preference_signal_type}"
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
                        signal_type=preference_signal_type,
                    )
                    logger.info(
                        f"Queued preference update: user={user_id[:8]}... "
                        f"entry={entry_id[:8]}... signal={preference_signal_type}"
                    )
                else:
                    logger.debug(
                        f"Preference update debounced: user={user_id[:8]}... "
                        f"entry={entry_id[:8]}... signal={preference_signal_type}"
                    )
            except Exception as e:
                # Don't fail the request if task queueing fails
                # The user's like/dislike is already saved
                logger.warning(f"Failed to queue preference update: {e}")
                pass

        # Return updated entry
        return await self.get_entry(entry_id, user_id)

    async def mark_all_read(
        self, user_id: str, feed_id: str | None = None, folder_id: str | None = None
    ) -> None:
        """
        Mark all entries as read.

        Args:
            user_id: User identifier.
            feed_id: Optional feed filter.
            folder_id: Optional folder filter.
        """
        # Get user's subscribed feed IDs
        subscriptions_stmt = select(Subscription.feed_id).where(Subscription.user_id == user_id)

        # If folder_id is provided, filter by feeds in that folder
        if folder_id:
            folder_ids = await self._get_folder_tree_ids(folder_id, user_id)
            subscriptions_stmt = subscriptions_stmt.where(Subscription.folder_id.in_(folder_ids))

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
