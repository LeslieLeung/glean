"""
Simple score service for non-vector Smart view.

Provides basic recommendation scoring using non-vector signals like
source affinity, author affinity, and recency when vectorization is disabled.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Entry, UserPreferenceStats


class SimpleScoreService:
    """
    Basic scoring service without vector embeddings.

    Uses non-vector signals for recommendations:
    - Source affinity: How often user reads/likes from this feed
    - Author affinity: How often user likes this author
    - Recency: Newer articles score higher
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize simple score service.

        Args:
            session: Database session.
        """
        self.session = session
        self._user_stats_cache: dict[str, UserPreferenceStats | None] = {}

    async def _get_user_stats(self, user_id: str) -> UserPreferenceStats | None:
        """Get user preference stats with caching."""
        if user_id not in self._user_stats_cache:
            result = await self.session.execute(
                select(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
            )
            self._user_stats_cache[user_id] = result.scalar_one_or_none()
        return self._user_stats_cache[user_id]

    def _calculate_recency_factor(self, published_at: datetime | None) -> float:
        """
        Calculate recency factor (0.0 to 1.0).

        - Last 24 hours: 1.0
        - 1-7 days: 0.5-1.0 linear decay
        - 7+ days: 0.0-0.5 slower decay
        """
        if not published_at:
            return 0.5  # Default for entries without publish date

        now = datetime.now(UTC)
        # Handle timezone-naive datetimes
        if published_at.tzinfo is None:
            age_hours = (now.replace(tzinfo=None) - published_at).total_seconds() / 3600
        else:
            age_hours = (now - published_at).total_seconds() / 3600

        if age_hours < 0:
            # Future date (scheduled post?)
            return 1.0
        elif age_hours <= 24:
            return 1.0
        elif age_hours <= 168:  # 7 days
            # Linear decay from 1.0 to 0.5 over 6 days
            return 1.0 - (age_hours - 24) / 288  # (168-24) * 2
        else:
            # Slower decay after 7 days
            days_over_week = (age_hours - 168) / 24
            return max(0.0, 0.5 - days_over_week * 0.02)

    def _get_source_affinity(self, stats: UserPreferenceStats | None, feed_id: str) -> float:
        """
        Get source affinity score for a feed.

        Returns a value between 0.0 and 1.0 based on user's interaction
        with the feed (likes vs dislikes ratio).
        """
        if not stats or not stats.source_affinity:
            return 0.5  # Neutral for new users

        feed_data = stats.source_affinity.get(feed_id, {})
        positive = feed_data.get("positive", 0)
        negative = feed_data.get("negative", 0)
        total = positive + negative

        if total == 0:
            return 0.5  # Neutral for unseen feeds

        # Calculate ratio with smoothing
        ratio = (positive + 1) / (total + 2)  # Add-1 smoothing
        return ratio

    def _get_author_affinity(self, stats: UserPreferenceStats | None, author: str | None) -> float:
        """
        Get author affinity score.

        Returns a value between 0.0 and 1.0 based on user's interaction
        with articles by this author.
        """
        if not stats or not stats.author_affinity or not author:
            return 0.5  # Neutral

        author_data = stats.author_affinity.get(author, {})
        positive = author_data.get("positive", 0)
        negative = author_data.get("negative", 0)
        total = positive + negative

        if total == 0:
            return 0.5  # Neutral for unknown authors

        # Calculate ratio with smoothing
        ratio = (positive + 1) / (total + 2)
        return ratio

    async def calculate_score(
        self,
        user_id: str,
        entry: Entry,
    ) -> dict[str, Any]:
        """
        Calculate preference score for an entry using non-vector signals.

        Args:
            user_id: User UUID.
            entry: Entry model instance.

        Returns:
            Dictionary with score and factors.
        """
        stats = await self._get_user_stats(user_id)

        # Calculate individual factors
        recency = self._calculate_recency_factor(entry.published_at)
        source_affinity = self._get_source_affinity(stats, entry.feed_id)
        author_affinity = self._get_author_affinity(stats, entry.author)

        # Weighted combination
        # Weights: source (40%), recency (35%), author (25%)
        score = 50.0  # Base score

        # Source affinity contribution: -20 to +20
        score += (source_affinity - 0.5) * 40

        # Recency contribution: -10 to +17.5
        score += (recency - 0.5) * 35

        # Author affinity contribution: -12.5 to +12.5
        score += (author_affinity - 0.5) * 25

        # Clamp to 0-100 range
        score = max(0.0, min(100.0, score))

        return {
            "score": score,
            "factors": {
                "source_affinity": round(source_affinity, 3),
                "author_affinity": round(author_affinity, 3),
                "recency": round(recency, 3),
                "method": "simple",  # Indicate non-vector scoring
            },
        }

    async def batch_calculate_scores(
        self,
        user_id: str,
        entries: list[Entry],
    ) -> dict[str, dict[str, Any]]:
        """
        Calculate scores for multiple entries.

        Args:
            user_id: User UUID.
            entries: List of Entry model instances.

        Returns:
            Dictionary mapping entry_id to score info.
        """
        # Pre-fetch user stats once
        await self._get_user_stats(user_id)

        results: dict[str, dict[str, Any]] = {}
        for entry in entries:
            results[entry.id] = await self.calculate_score(user_id, entry)

        return results

    async def get_recommendation_summary(self, user_id: str) -> dict[str, Any]:
        """
        Get a summary of the user's preference model for debugging/display.

        Args:
            user_id: User UUID.

        Returns:
            Summary dictionary.
        """
        stats = await self._get_user_stats(user_id)

        if not stats:
            return {
                "has_data": False,
                "message": "No preference data yet. Like or bookmark articles to improve recommendations.",
            }

        total_signals = stats.positive_count + stats.negative_count

        return {
            "has_data": True,
            "total_signals": total_signals,
            "positive_ratio": stats.positive_count / max(1, total_signals),
            "top_sources_count": len(stats.source_affinity),
            "top_authors_count": len(stats.author_affinity),
            "method": "simple",
        }
