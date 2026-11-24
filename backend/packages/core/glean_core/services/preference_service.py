"""Feedback totals shown in user settings."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Bookmark, Entry, UserEntry

from .entry_dedup import url_user_entry_id


class PreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_stats(self, user_id: str) -> dict[str, int]:
        result = await self.db.execute(
            select(
                func.count().filter(UserEntry.is_liked.is_(True)),
                func.count().filter(UserEntry.is_liked.is_(False)),
            )
            .select_from(UserEntry)
            .join(Entry, Entry.id == UserEntry.entry_id)
            .where(UserEntry.user_id == user_id, UserEntry.id == url_user_entry_id(user_id))
        )
        likes, dislikes = result.one()
        bookmarks = await self.db.scalar(
            select(func.count()).select_from(Bookmark).where(Bookmark.user_id == user_id)
        )
        return {"total_likes": likes, "total_dislikes": dislikes, "total_bookmarks": bookmarks or 0}
