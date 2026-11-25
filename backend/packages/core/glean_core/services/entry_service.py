"""
Entry service.

Handles entry retrieval and user-specific entry state management.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from arq.connections import ArqRedis
from sqlalchemy import Select, and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.published_at import FUTURE_PUBLISHED_AT_TOLERANCE, effective_published_at
from glean_core.schemas import EntryListResponse, EntryResponse, UpdateEntryStateRequest
from glean_core.schemas.entry import RecommendationReason
from glean_core.schemas.systemone import SystemOneConfig
from glean_core.services.systemone_service import classification_for_display
from glean_core.services.typed_config_service import TypedConfigService
from glean_database.models import (
    Bookmark,
    Entry,
    Feed,
    Folder,
    Subscription,
    User,
    UserEntry,
)

from .entry_dedup import linkless_entry_id, url_user_entry_id
from .entry_rank_snapshot import SmartSnapshot, smart_scope
from .entry_ranker import (
    FEEDBACK_LIMIT,
    GLOBAL_CANDIDATE_LIMIT,
    GLOBAL_WINDOW_DAYS,
    SCORE_BATCH_SIZE,
    EmbeddingReader,
    EntryRanker,
    RankedEntry,
    RankEntry,
    rank_entries,
)

logger = get_logger(__name__)


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
        include_score: bool = False,
        global_smart: bool = False,
        use_cursor: bool = False,
        cursor: str | None = None,
        get_embeddings: Callable[[], Awaitable[EmbeddingReader | None]] | None = None,
    ) -> EntryListResponse:
        """
        Get entries for a user with filtering and pagination.

        Exact matching non-empty URLs appear once within the selected feeds/folders,
        preferring the earliest subscription. State is shared by URL per user.

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
            include_score: Calculate recommendation scores on a timeline page.
            global_smart: Use the recent unread candidate pool and source diversification.
            use_cursor: Request stable Smart pagination.
            cursor: Resume a Smart snapshot.
            get_embeddings: Load optional article embeddings for current scoring.

        Returns:
            Paginated entry list response.
        """

        now = datetime.now(UTC)
        global_smart = view == "smart" and global_smart and not feed_id and not folder_id
        if global_smart:
            is_read = False

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
            return EntryListResponse(items=[], total=0, page=page, per_page=per_page, total_pages=0)

        # Pick one stable representative per URL within the requested scope,
        # before counting, scoring or paginating. Earlier subscriptions win.
        candidates = (
            select(
                Entry.id.label("entry_id"),
                func.row_number()
                .over(
                    partition_by=(Entry.url, linkless_entry_id()),
                    order_by=(Subscription.created_at, Entry.created_at, Entry.id),
                )
                .label("url_rank"),
            )
            .join(Subscription, Subscription.feed_id == Entry.feed_id)
            .where(Subscription.user_id == user_id, Entry.feed_id.in_(feed_ids))
        )
        if feed_id:
            candidates = candidates.where(Entry.feed_id == feed_id)
        ranked_entries = candidates.subquery()
        unique_ids = select(ranked_entries.c.entry_id).where(ranked_entries.c.url_rank == 1)
        classification_config = await TypedConfigService(self.session).get(SystemOneConfig)

        # Subquery to get bookmark_id for entry (limit 1 in case of duplicates)
        bookmark_id_subq = (
            select(Bookmark.id)
            .where(Bookmark.user_id == user_id)
            .where(
                or_(
                    Bookmark.entry_id == Entry.id,
                    and_(Entry.url != "", Bookmark.url == Entry.url),
                )
            )
            .correlate(Entry)
            .order_by(Bookmark.created_at, Bookmark.id)
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
            .join_from(Entry, Feed, Entry.feed_id == Feed.id)
            .outerjoin_from(
                Entry,
                UserEntry,
                UserEntry.id == url_user_entry_id(user_id),
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

        recommendations: dict[str, tuple[float, RecommendationReason]]
        if view == "smart":
            ranked: list[RankedEntry] = []
            snapshot = None
            scope = smart_scope(
                user_id, feed_id, folder_id, is_read, is_liked, read_later, global_smart
            )
            if cursor is not None:
                if self.redis_pool is None:
                    raise RuntimeError("Smart cursor pagination requires Redis")
                snapshot = await SmartSnapshot.load(self.redis_pool, scope, cursor)
            else:
                score_stmt = stmt.where(Entry.id.in_(unique_ids)).with_only_columns(
                    Entry.id,
                    Entry.feed_id,
                    Entry.published_at,
                    Entry.created_at,
                    Entry.title,
                    Entry.summary,
                    UserEntry.is_liked,
                    maintain_column_froms=True,
                )
                if global_smart:
                    published_at = case(
                        (
                            or_(
                                Entry.published_at.is_(None),
                                Entry.published_at > now + FUTURE_PUBLISHED_AT_TOLERANCE,
                            ),
                            Entry.created_at,
                        ),
                        else_=Entry.published_at,
                    )
                    score_stmt = (
                        score_stmt.where(published_at >= now - timedelta(days=GLOBAL_WINDOW_DAYS))
                        .order_by(published_at.desc(), Entry.id)
                        .limit(GLOBAL_CANDIDATE_LIMIT)
                    )
                ranked = await self._rank_entries(
                    user_id, score_stmt, now, global_smart, get_embeddings
                )
                if use_cursor and len(ranked) > per_page:
                    if self.redis_pool is None:
                        raise RuntimeError("Smart cursor pagination requires Redis")
                    snapshot = await SmartSnapshot.create(self.redis_pool, scope, ranked)

            if snapshot is not None:
                rows, recommendations, offset = await self._read_smart_page(
                    stmt, snapshot, per_page
                )
                total = len(snapshot.entries)
                next_cursor = snapshot.cursor(offset)
            else:
                total = len(ranked)
                start = 0 if use_cursor else (page - 1) * per_page
                recommendations = {
                    entry.id: (entry.score, entry.reason)
                    for entry in ranked[start : start + per_page]
                }
                eligible = await self._ranked_rows(stmt, list(recommendations))
                rows = [eligible[entry_id] for entry_id in recommendations if entry_id in eligible]
                next_cursor = None
        else:
            stmt = stmt.where(Entry.id.in_(unique_ids))
            total = (
                await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            )
            result = await self.session.execute(
                stmt.order_by(desc(Entry.published_at), Entry.id)
                .limit(per_page)
                .offset((page - 1) * per_page)
            )
            rows = result.all()
            recommendations = {}
            if include_score and rows:
                ranker = await self._entry_ranker(user_id, now, get_embeddings)
                scored = await ranker.score(
                    [
                        RankEntry(
                            entry.id,
                            entry.feed_id,
                            effective_published_at(entry.published_at, entry.created_at, now=now),
                            entry.title,
                            entry.summary,
                            state.is_liked if state else None,
                        )
                        for entry, state, *_ in rows
                    ]
                )
                recommendations = {entry.id: (entry.score, entry.reason) for entry in scored}
            next_cursor = None

        items: list[EntryResponse] = []
        for entry, state, bookmark_id, feed_title, feed_icon_url in rows:
            score, reason = recommendations.get(entry.id, (None, None))
            items.append(
                EntryResponse(
                    id=entry.id,
                    feed_id=entry.feed_id,
                    url=entry.url,
                    title=entry.title,
                    author=entry.author,
                    content=entry.content,
                    summary=entry.summary,
                    classification=classification_for_display(
                        entry.classification_result, classification_config
                    ),
                    classification_status=entry.classification_status
                    if classification_config.enabled
                    else None,
                    published_at=effective_published_at(
                        entry.published_at, entry.created_at, now=now
                    ),
                    created_at=entry.created_at,
                    is_read=state.is_read if state else False,
                    is_liked=state.is_liked if state else None,
                    read_later=state.read_later if state else False,
                    read_later_until=state.read_later_until if state else None,
                    read_at=state.read_at if state else None,
                    is_bookmarked=bookmark_id is not None,
                    bookmark_id=bookmark_id,
                    preference_score=score,
                    recommendation_reason=reason,
                    feed_title=feed_title,
                    feed_icon_url=feed_icon_url,
                )
            )
        return EntryListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=(total + per_page - 1) // per_page,
            next_cursor=next_cursor,
        )

    async def _entry_ranker(
        self,
        user_id: str,
        now: datetime,
        get_embeddings: Callable[[], Awaitable[EmbeddingReader | None]] | None,
    ) -> EntryRanker:
        # Resolve URL-shared state before limiting each polarity so legacy copies
        # and retracted reactions cannot supply duplicate or stale feedback.
        feedback = (
            select(
                Entry.id,
                Entry.feed_id,
                Entry.published_at,
                Entry.created_at,
                Entry.title,
                Entry.summary,
                UserEntry.is_liked,
                func.row_number()
                .over(
                    partition_by=UserEntry.is_liked,
                    order_by=(UserEntry.liked_at.desc().nulls_last(), UserEntry.id),
                )
                .label("feedback_rank"),
            )
            .join_from(Entry, UserEntry, UserEntry.entry_id == Entry.id)
            .where(
                UserEntry.user_id == user_id,
                UserEntry.is_liked.is_not(None),
                UserEntry.id == url_user_entry_id(user_id),
            )
            .subquery()
        )
        result = await self.session.execute(
            select(
                feedback.c.id,
                feedback.c.feed_id,
                feedback.c.published_at,
                feedback.c.created_at,
                feedback.c.title,
                feedback.c.summary,
                feedback.c.is_liked,
            ).where(feedback.c.feedback_rank <= FEEDBACK_LIMIT)
        )
        samples = [
            RankEntry(
                entry_id,
                feed_id,
                effective_published_at(published_at, created_at, now=now),
                title,
                summary,
                reaction,
            )
            for entry_id, feed_id, published_at, created_at, title, summary, reaction in result
        ]
        embeddings = await get_embeddings() if samples and get_embeddings else None
        ranker = EntryRanker(now, samples, embeddings)
        await ranker.load_feedback_vectors()
        return ranker

    async def _rank_entries(
        self,
        user_id: str,
        stmt: Select[Any],
        now: datetime,
        global_smart: bool,
        get_embeddings: Callable[[], Awaitable[EmbeddingReader | None]] | None,
    ) -> list[RankedEntry]:
        ranker = await self._entry_ranker(user_id, now, get_embeddings)
        result = await self.session.stream(stmt.execution_options(yield_per=SCORE_BATCH_SIZE))
        scored: list[RankedEntry] = []
        try:
            async for batch in result.partitions():
                scored.extend(
                    await ranker.score(
                        [
                            RankEntry(
                                entry_id,
                                feed_id,
                                effective_published_at(published_at, created_at, now=now),
                                title,
                                summary,
                                reaction,
                            )
                            for entry_id, feed_id, published_at, created_at, title, summary, reaction in batch
                        ]
                    )
                )
        finally:
            await result.close()
        return rank_entries(scored, diversify=global_smart)

    async def _ranked_rows(self, stmt: Select[Any], ids: list[str]) -> dict[str, Any]:
        if not ids:
            return {}
        result = await self.session.execute(stmt.where(Entry.id.in_(ids)))
        return {row[0].id: row for row in result}

    async def _read_smart_page(
        self, stmt: Select[Any], snapshot: SmartSnapshot, per_page: int
    ) -> tuple[list[Any], dict[str, tuple[float, RecommendationReason]], int]:
        offset = snapshot.offset
        recommendations: dict[str, tuple[float, RecommendationReason]] = {}
        id_stmt = stmt.with_only_columns(Entry.id, maintain_column_froms=True)
        while offset < len(snapshot.entries) and len(recommendations) < per_page:
            batch = snapshot.entries[offset : offset + SCORE_BATCH_SIZE]
            result = await self.session.scalars(
                id_stmt.where(Entry.id.in_([entry_id for entry_id, _, _ in batch]))
            )
            eligible = set(result)
            for entry_id, score, reason in batch:
                offset += 1
                if entry_id in eligible:
                    recommendations[entry_id] = (score, reason)
                if len(recommendations) == per_page:
                    break

        rows = await self._ranked_rows(stmt, list(recommendations))
        return (
            [rows[entry_id] for entry_id in recommendations if entry_id in rows],
            recommendations,
            offset,
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
        classification_config = await TypedConfigService(self.session).get(SystemOneConfig)

        # Subquery to get bookmark_id for entry (limit 1 in case of duplicates)
        bookmark_id_subq = (
            select(Bookmark.id)
            .where(Bookmark.user_id == user_id)
            .where(
                or_(
                    Bookmark.entry_id == Entry.id,
                    and_(Entry.url != "", Bookmark.url == Entry.url),
                )
            )
            .correlate(Entry)
            .order_by(Bookmark.created_at, Bookmark.id)
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
                UserEntry.id == url_user_entry_id(user_id),
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
            classification=classification_for_display(
                entry.classification_result, classification_config
            ),
            classification_status=entry.classification_status
            if classification_config.enabled
            else None,
            published_at=effective_published_at(entry.published_at, entry.created_at),
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
        stmt = select(UserEntry).where(
            UserEntry.id == url_user_entry_id(user_id, entry.url, entry.id)
        )
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
            new_is_liked = update.is_liked

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
        entries_stmt = (
            select(Entry.id, Entry.url)
            .where(Entry.feed_id.in_(feed_ids))
            .order_by(Entry.created_at, Entry.id)
        )
        if feed_id:
            entries_stmt = entries_stmt.where(Entry.feed_id == feed_id)

        result = await self.session.execute(entries_stmt)
        entry_ids_by_article: dict[tuple[str, str | None], str] = {}
        for entry_id, url in result.all():
            entry_ids_by_article.setdefault((url, None if url else entry_id), entry_id)

        # Update or create UserEntry records
        now = datetime.now(UTC)
        for (url, _), entry_id in entry_ids_by_article.items():
            stmt = select(UserEntry).where(
                UserEntry.id == url_user_entry_id(user_id, url, entry_id)
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
