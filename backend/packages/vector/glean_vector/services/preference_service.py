"""User preference model service."""

import contextlib
from datetime import UTC, datetime
from typing import Any

import numpy as np
from redis.asyncio import Redis
from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import RedisKeys
from glean_database.models import Bookmark, Entry, UserEntry, UserPreferenceStats
from glean_vector.clients.vector_store import VectorStoreClient
from glean_vector.config import preference_config


class PreferenceEmbeddingsNotReadyError(RuntimeError):
    """Raised when current preference history references embeddings not ready yet."""

    def __init__(self, entry_ids: list[str]) -> None:
        self.entry_ids = entry_ids
        super().__init__(
            f"Preference embeddings are not ready for {len(entry_ids)} entr"
            f"{'y' if len(entry_ids) == 1 else 'ies'}"
        )


async def get_preference_history_user_ids(session: AsyncSession) -> list[str]:
    """Return users with a current reaction or entry-backed bookmark."""
    history_users = union(
        select(UserEntry.user_id).where(UserEntry.is_liked.is_not(None)),
        select(Bookmark.user_id).where(Bookmark.entry_id.is_not(None)),
    )
    result = await session.execute(history_users)
    return [str(row[0]) for row in result.all()]


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
        vector_client: VectorStoreClient,
        redis_client: Redis | None = None,
    ) -> None:
        """
        Initialize preference service.

        Args:
            db_session: Database session
            vector_client: Vector database client
            redis_client: Redis client for distributed locks (optional but recommended)
        """
        self.db = db_session
        self.vector_client = vector_client
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

        # Event payloads are deliberately treated as wake-up notifications,
        # not as the source of truth. Rebuilding from the user's current DB
        # state makes duplicate/out-of-order jobs and reaction transitions
        # idempotent.
        await self.rebuild_from_history(user_id)

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
            lock_key = RedisKeys.preference_lock(user_id, vector_type)
            lock = self.redis.lock(
                lock_key,
                timeout=RedisKeys.PREFERENCE_LOCK_TTL,
                blocking_timeout=RedisKeys.PREFERENCE_LOCK_BLOCKING_TIMEOUT,
            )

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
        prefs = await self.vector_client.get_user_preferences(user_id)
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

        # Store in vector backend
        await self.vector_client.upsert_user_preference(
            user_id=user_id,
            vector_type=vector_type,
            embedding=new_embedding.tolist(),
            sample_count=new_count,
            updated_at=int(datetime.now(UTC).timestamp()),
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

    async def rebuild_from_history(
        self,
        user_id: str,
        *,
        allow_failed_embeddings: bool = False,
    ) -> None:
        """
        Rebuild user preference model from scratch using historical data.

        Args:
            user_id: User UUID
            allow_failed_embeddings: Skip entries whose embedding generation
                reached the terminal ``failed`` state. Full embedding rebuilds
                use this after every entry has become terminal.
        """
        if self.redis:
            lock_key = RedisKeys.preference_lock(user_id, "model")
            lock = self.redis.lock(
                lock_key,
                timeout=RedisKeys.PREFERENCE_MODEL_LOCK_TTL,
                blocking_timeout=RedisKeys.PREFERENCE_LOCK_BLOCKING_TIMEOUT,
            )
            acquired = False
            try:
                acquired = await lock.acquire()
                if not acquired:
                    raise TimeoutError(
                        f"Failed to acquire lock for user {user_id} preference rebuild"
                    )
                await self._rebuild_from_history_locked(
                    user_id,
                    allow_failed_embeddings=allow_failed_embeddings,
                )
                # Keep the DB commit inside the same user-wide critical
                # section as the vector replacement. Otherwise a second
                # first-signal task could race the unique stats row.
                await self.db.commit()
            finally:
                if acquired:
                    with contextlib.suppress(Exception):
                        await lock.release()
            return

        await self._rebuild_from_history_locked(
            user_id,
            allow_failed_embeddings=allow_failed_embeddings,
        )
        await self.db.commit()

    async def _rebuild_from_history_locked(
        self,
        user_id: str,
        *,
        allow_failed_embeddings: bool,
    ) -> None:
        """Recalculate vector and affinity state while holding the user lock."""
        reactions_result = await self.db.execute(
            select(UserEntry, Entry)
            .join(Entry, UserEntry.entry_id == Entry.id)
            .where(UserEntry.user_id == user_id)
            .where(UserEntry.is_liked.is_not(None))
        )
        bookmark_result = await self.db.execute(
            select(Bookmark, Entry)
            .join(Entry, Bookmark.entry_id == Entry.id)
            .where(Bookmark.user_id == user_id, Bookmark.entry_id.is_not(None))
        )

        signals: list[tuple[Entry, float]] = []
        for user_entry, entry in reactions_result.all():
            if user_entry.is_liked is True:
                signals.append((entry, self.SIGNAL_WEIGHTS["like"]))
            elif user_entry.is_liked is False:
                signals.append((entry, self.SIGNAL_WEIGHTS["dislike"]))
        signals.extend(
            (entry, self.SIGNAL_WEIGHTS["bookmark"]) for _bookmark, entry in bookmark_result.all()
        )

        entry_ids = list(dict.fromkeys(entry.id for entry, _weight in signals))
        embeddings = (
            await self.vector_client.batch_get_entry_embeddings(entry_ids) if entry_ids else {}
        )

        missing: list[str] = []
        usable_signals: list[tuple[Entry, float, list[float]]] = []
        for entry, weight in signals:
            embedding = embeddings.get(entry.id)
            if embedding is not None:
                usable_signals.append((entry, weight, embedding))
                continue
            if allow_failed_embeddings and entry.embedding_status == "failed":
                continue
            missing.append(entry.id)

        # Never clear a usable existing model while an embedding is merely
        # delayed. The worker converts this into an arq Retry.
        if missing:
            raise PreferenceEmbeddingsNotReadyError(list(dict.fromkeys(missing)))

        positive_vectors: list[np.ndarray[Any, np.dtype[np.float64]]] = []
        positive_weights: list[float] = []
        negative_vectors: list[np.ndarray[Any, np.dtype[np.float64]]] = []
        negative_weights: list[float] = []
        source_affinity: dict[str, dict[str, float]] = {}
        author_affinity: dict[str, dict[str, float]] = {}

        for entry, weight, embedding in usable_signals:
            abs_weight = abs(weight)
            key = "positive" if weight > 0 else "negative"
            target_vectors = positive_vectors if weight > 0 else negative_vectors
            target_weights = positive_weights if weight > 0 else negative_weights
            target_vectors.append(np.asarray(embedding, dtype=np.float64))
            target_weights.append(abs_weight)

            source = source_affinity.setdefault(
                entry.feed_id,
                {"positive": 0.0, "negative": 0.0},
            )
            source[key] += abs_weight
            if entry.author:
                author = author_affinity.setdefault(
                    entry.author,
                    {"positive": 0.0, "negative": 0.0},
                )
                author[key] += abs_weight

        # All inputs are now available and the replacement state has been
        # calculated. From here onward, retries are safe and idempotent.
        await self.vector_client.delete_user_preferences(user_id)
        updated_at = int(datetime.now(UTC).timestamp())

        async def store_vector(
            vector_type: str,
            vectors: list[np.ndarray[Any, np.dtype[np.float64]]],
            weights: list[float],
        ) -> None:
            if not vectors:
                return
            combined = np.average(np.stack(vectors), axis=0, weights=np.asarray(weights))
            norm = np.linalg.norm(combined)
            if norm > 1e-8:
                combined = combined / norm
            await self.vector_client.upsert_user_preference(
                user_id=user_id,
                vector_type=vector_type,
                embedding=combined.tolist(),
                sample_count=sum(weights),
                updated_at=updated_at,
            )

        await store_vector("positive", positive_vectors, positive_weights)
        await store_vector("negative", negative_vectors, negative_weights)

        stats_result = await self.db.execute(
            select(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
        )
        stats = stats_result.scalar_one_or_none()
        if not usable_signals:
            if stats:
                await self.db.delete(stats)
            await self.db.flush()
            return

        if stats is None:
            stats = UserPreferenceStats(user_id=user_id)
            self.db.add(stats)

        stats.positive_count = sum(positive_weights)
        stats.negative_count = sum(negative_weights)
        stats.source_affinity = source_affinity
        stats.author_affinity = author_affinity
        await self.db.flush()

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

        Args:
            user_id: User UUID
            entry_id: Entry UUID
            signal_type: Signal type to remove
        """
        if signal_type not in self.SIGNAL_WEIGHTS:
            raise ValueError(f"Invalid signal type: {signal_type}")
        await self.rebuild_from_history(user_id)
