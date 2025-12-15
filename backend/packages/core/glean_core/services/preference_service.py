"""Preference service."""

from typing import Any

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Bookmark, Feed, UserEntry, UserPreferenceStats


class PreferenceService:
    """
    Service for preference operations.

    This service provides high-level preference operations,
    delegating heavy computation to background workers.
    """

    def __init__(self, session: AsyncSession, redis_pool: ArqRedis) -> None:
        """
        Initialize preference service.

        Args:
            session: Database session
            redis_pool: Redis connection pool for task queue
        """
        self.db = session
        self.redis = redis_pool

    async def get_stats(self, user_id: str) -> dict[str, Any]:
        """
        Get user preference statistics.

        Args:
            user_id: User UUID

        Returns:
            Statistics dictionary
        """
        # Get stats from database
        result = await self.db.execute(
            select(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
        )
        stats = result.scalar_one_or_none()

        # Get counts from UserEntry
        result = await self.db.execute(select(UserEntry).where(UserEntry.user_id == user_id))
        user_entries = result.scalars().all()

        total_likes = sum(1 for ue in user_entries if ue.is_liked is True)
        total_dislikes = sum(1 for ue in user_entries if ue.is_liked is False)

        # Get bookmarks count
        result = await self.db.execute(select(Bookmark).where(Bookmark.user_id == user_id))
        bookmarks = result.scalars().all()
        total_bookmarks = len(bookmarks)

        # Calculate preference strength
        total_signals = total_likes + total_dislikes + total_bookmarks
        if total_signals < 5:
            strength = "weak"
        elif total_signals < 10:
            strength = "moderate"
        else:
            strength = "strong"

        # Get top sources and authors
        top_sources = []
        top_authors = []

        if stats:
            # Sort sources by affinity
            source_scores: list[dict[str, Any]] = []
            for feed_id, affinity in stats.source_affinity.items():
                pos = affinity.get("positive", 0)
                neg = affinity.get("negative", 0)
                total = pos + neg
                if total > 0:
                    score = (pos - neg) / total
                    source_scores.append({"feed_id": feed_id, "affinity_score": round(score, 2)})

            top_sources_raw: list[dict[str, Any]] = sorted(
                source_scores,
                key=lambda x: x["affinity_score"],
                reverse=True,
            )[:5]

            # Fetch feed titles for top sources
            if top_sources_raw:
                feed_ids = [s["feed_id"] for s in top_sources_raw]
                result = await self.db.execute(select(Feed).where(Feed.id.in_(feed_ids)))
                feeds = {f.id: f for f in result.scalars().all()}
                top_sources = [
                    {
                        "feed_id": s["feed_id"],
                        "feed_title": feeds[s["feed_id"]].title
                        if s["feed_id"] in feeds and feeds[s["feed_id"]].title
                        else "Unknown Feed",
                        "affinity_score": s["affinity_score"],
                    }
                    for s in top_sources_raw
                ]
            else:
                top_sources = []

            # Sort authors by affinity
            author_scores: list[dict[str, Any]] = []
            for author, affinity in stats.author_affinity.items():
                pos = affinity.get("positive", 0)
                neg = affinity.get("negative", 0)
                total = pos + neg
                if total > 0:
                    score = (pos - neg) / total
                    author_scores.append({"name": author, "affinity_score": round(score, 2)})

            top_authors: list[dict[str, Any]] = sorted(
                author_scores, key=lambda x: x["affinity_score"], reverse=True
            )[:5]

        return {
            "total_likes": total_likes,
            "total_dislikes": total_dislikes,
            "total_bookmarks": total_bookmarks,
            "preference_strength": strength,
            "top_sources": top_sources,
            "top_authors": top_authors,
            "model_updated_at": stats.updated_at if stats else None,
        }

    async def queue_rebuild(self, user_id: str) -> None:
        """
        Queue preference model rebuild task.

        Args:
            user_id: User UUID
        """
        await self.redis.enqueue_job(
            "rebuild_user_preference",
            user_id=user_id,
        )

    async def get_strength(self, user_id: str) -> str:
        """
        Get preference model strength.

        Args:
            user_id: User UUID

        Returns:
            Strength indicator ("weak", "moderate", "strong")
        """
        result = await self.db.execute(
            select(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
        )
        stats = result.scalar_one_or_none()

        if not stats:
            return "weak"

        total = stats.positive_count + stats.negative_count

        if total < 5:
            return "weak"
        elif total < 10:
            return "moderate"
        else:
            return "strong"
