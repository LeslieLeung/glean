"""Durable preference-rebuild outbox helpers."""

from collections.abc import Iterable

from sqlalchemy import select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Bookmark, Entry, Subscription, User, UserEntry


async def get_feed_preference_user_ids(session: AsyncSession, feed_id: str) -> list[str]:
    """Include saved/reaction history even when its owner no longer subscribes."""
    result = await session.execute(
        union(
            select(Subscription.user_id).where(Subscription.feed_id == feed_id),
            select(UserEntry.user_id)
            .join(Entry, UserEntry.entry_id == Entry.id)
            .where(Entry.feed_id == feed_id, UserEntry.is_liked.is_not(None)),
            select(Bookmark.user_id)
            .join(Entry, Bookmark.entry_id == Entry.id)
            .where(Entry.feed_id == feed_id),
        )
    )
    return [str(user_id) for user_id in result.scalars().all()]


async def mark_preferences_dirty(
    session: AsyncSession,
    user_ids: Iterable[str],
) -> int:
    """Increment preference revisions in the caller's transaction."""
    unique_user_ids = list(dict.fromkeys(str(user_id) for user_id in user_ids))
    if not unique_user_ids:
        return 0
    result = await session.execute(
        update(User)
        .where(User.id.in_(unique_user_ids))
        .values(preference_revision=User.preference_revision + 1)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
