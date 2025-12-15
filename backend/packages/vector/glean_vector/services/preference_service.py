"""User preference model service."""

import contextlib
from datetime import datetime

import numpy as np
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Entry, UserEntry, UserPreferenceStats
from glean_vector.clients.milvus_client import MilvusClient
from glean_vector.config import preference_config


class PreferenceService:
    """
    Service for managing user preference models.

    Handles:
    1. Preference signal processing (like/dislike/bookmark)
    2. Preference vector updates (moving average)
    3. Affinity statistics (source/author)
    """

    SIGNAL_WEIGHTS = {
        "like": 1.0,
        "dislike": -1.0,
        "bookmark": 0.7,
    }

    def __init__(
        self,
        db_session: AsyncSession,
        milvus_client: MilvusClient,
        redis_client: Redis | None = None,
    ) -> None:
        """
        Initialize preference service.

        Args:
            db_session: Database session
            milvus_client: Milvus vector database client
            redis_client: Redis client for distributed locks (optional but recommended)
        """
        self.db = db_session
        self.milvus = milvus_client
        self.redis = redis_client
        self.config = preference_config

    async def handle_preference_signal(
        self,
        user_id: str,
        entry_id: str,
        signal_type: str,
    ) -> None:
        """
        Handle user preference signal.

        Args:
            user_id: User UUID
            signal_type: "like", "dislike", or "bookmark"
        """
        if signal_type not in self.SIGNAL_WEIGHTS:
            raise ValueError(f"Invalid signal type: {signal_type}")

        weight = self.SIGNAL_WEIGHTS[signal_type]

        # Get entry embedding from Milvus
        embedding = await self.milvus.get_entry_embedding(entry_id)
        if not embedding:
            # Entry not yet embedded, skip preference update
            return

        # Get entry metadata for affinity tracking
        result = await self.db.execute(select(Entry).where(Entry.id == entry_id))
        entry = result.scalar_one_or_none()
        if not entry:
            return

        # Update preference vector
        await self._update_preference_vector(user_id, embedding, weight)

        # Update affinity statistics
        await self._update_affinity_stats(
            user_id=user_id,
            feed_id=entry.feed_id,
            author=entry.author,
            is_positive=weight > 0,
            weight=abs(weight),
        )

    async def _update_preference_vector(
        self,
        user_id: str,
        article_embedding: list[float],
        weight: float,
    ) -> None:
        """
        Update user preference vector using weighted moving average.

        Uses Redis locks to prevent race conditions when multiple signals
        are processed concurrently for the same user.

        Args:
            user_id: User UUID
            article_embedding: Entry embedding vector
            weight: Signal weight (positive or negative)
        """
        vector_type = "positive" if weight > 0 else "negative"
        abs_weight = abs(weight)

        # Use Redis lock if available to prevent race conditions
        if self.redis:
            lock_key = f"preference_lock:{user_id}:{vector_type}"
            lock = self.redis.lock(lock_key, timeout=10, blocking_timeout=5)

            try:
                # Acquire lock (blocks up to 5 seconds if another task holds it)
                acquired = await lock.acquire()
                if not acquired:
                    raise TimeoutError(
                        f"Failed to acquire lock for user {user_id} preference update"
                    )

                # Critical section: read-compute-write with lock protection
                await self._update_preference_vector_locked(
                    user_id, article_embedding, weight, vector_type, abs_weight
                )
            finally:
                # Always release the lock
                # Lock might have expired, ignore release errors
                with contextlib.suppress(Exception):
                    await lock.release()
        else:
            # No Redis available - proceed without lock (not recommended for production)
            await self._update_preference_vector_locked(
                user_id, article_embedding, weight, vector_type, abs_weight
            )

    async def _update_preference_vector_locked(
        self,
        user_id: str,
        article_embedding: list[float],
        weight: float,
        vector_type: str,
        abs_weight: float,
    ) -> None:
        """
        Internal method to update preference vector (must be called with lock held).

        Args:
            user_id: User UUID
            article_embedding: Entry embedding vector
            weight: Signal weight (positive or negative)
            vector_type: "positive" or "negative"
            abs_weight: Absolute value of weight
        """
        # Get current preference vectors
        prefs = await self.milvus.get_user_preferences(user_id)
        current = prefs.get(vector_type)

        if current is None:
            # First signal of this type - initialize
            new_embedding = np.array(article_embedding) * abs_weight
            new_count = abs_weight
        else:
            # Moving average
            old_embedding = np.array(current["embedding"])
            old_count = current["sample_count"]

            # Weighted average
            total_weight = old_count + abs_weight
            new_embedding = (
                old_embedding * old_count + np.array(article_embedding) * abs_weight
            ) / total_weight
            new_count = total_weight

        # Normalize to unit vector
        norm = np.linalg.norm(new_embedding)
        if norm > 1e-8:
            new_embedding = new_embedding / norm

        # Store in Milvus
        await self.milvus.upsert_user_preference(
            user_id=user_id,
            vector_type=vector_type,
            embedding=new_embedding.tolist(),
            sample_count=new_count,
            updated_at=int(datetime.now().timestamp()),
        )

    async def _update_affinity_stats(
        self,
        user_id: str,
        feed_id: str,
        author: str | None,
        is_positive: bool,
        weight: float,
    ) -> None:
        """
        Update source and author affinity statistics.

        Args:
            user_id: User UUID
            feed_id: Feed UUID
            author: Author name
            is_positive: True for like/bookmark, False for dislike
            weight: Signal weight
        """
        # Get or create stats record
        result = await self.db.execute(
            select(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
        )
        stats = result.scalar_one_or_none()

        if not stats:
            stats = UserPreferenceStats(
                user_id=user_id,
                positive_count=0.0,
                negative_count=0.0,
                source_affinity={},
                author_affinity={},
            )
            self.db.add(stats)

        # Update counts
        if is_positive:
            stats.positive_count += weight
        else:
            stats.negative_count += weight

        # Update source affinity
        if feed_id not in stats.source_affinity:
            stats.source_affinity[feed_id] = {"positive": 0, "negative": 0}

        key = "positive" if is_positive else "negative"
        stats.source_affinity[feed_id][key] += weight

        # Update author affinity
        if author:
            if author not in stats.author_affinity:
                stats.author_affinity[author] = {"positive": 0, "negative": 0}

            stats.author_affinity[author][key] += weight

        # Mark as updated (trigger JSONB update)
        stats.source_affinity = dict(stats.source_affinity)
        stats.author_affinity = dict(stats.author_affinity)

        # Flush changes to database (commit will be handled by session context manager)
        await self.db.flush()

    async def rebuild_from_history(self, user_id: str) -> None:
        """
        Rebuild user preference model from scratch using historical data.

        Args:
            user_id: User UUID
        """
        # Clear existing preferences from Milvus
        await self.milvus.delete_user_preferences(user_id)

        # Delete existing stats from database
        await self.db.execute(
            delete(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
        )
        # Flush deletion (commit will be handled by session context manager)
        await self.db.flush()

        # Get all user feedback
        result = await self.db.execute(
            select(UserEntry, Entry)
            .join(Entry, UserEntry.entry_id == Entry.id)
            .where(UserEntry.user_id == user_id)
            .where(
                UserEntry.is_liked.is_not(None)  # Has like/dislike
            )
        )
        user_entries = result.all()

        # Process likes and dislikes
        for user_entry, entry in user_entries:
            if user_entry.is_liked is True:
                await self.handle_preference_signal(user_id, entry.id, "like")
            elif user_entry.is_liked is False:
                await self.handle_preference_signal(user_id, entry.id, "dislike")

        # TODO: Process bookmarks if needed
        # This would require joining with Bookmark table

    async def get_preference_strength(self, user_id: str) -> str:
        """
        Calculate preference model strength.

        Args:
            user_id: User UUID

        Returns:
            "weak", "moderate", or "strong"
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
        elif total < self.config.confidence_threshold:
            return "moderate"
        else:
            return "strong"

    async def remove_preference_signal(
        self,
        user_id: str,
        entry_id: str,
        signal_type: str,
    ) -> None:
        """
        Remove a preference signal (e.g., unlike).

        Note: This is complex as we can't easily "subtract" from a moving average.
        For now, we recommend rebuilding the model periodically.

        Args:
            user_id: User UUID
            entry_id: Entry UUID
            signal_type: Signal type to remove
        """
        # TODO: Implement if needed
        # For MVP, we can rebuild the entire model when needed
        pass
