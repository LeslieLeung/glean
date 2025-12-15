"""Preference score calculation service."""

from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Entry, UserPreferenceStats
from glean_vector.clients.milvus_client import MilvusClient
from glean_vector.config import preference_config


class ScoreService:
    """
    Service for calculating preference scores in real-time.

    Uses cosine similarity between entry embeddings and user preference vectors,
    combined with source/author affinity boosts.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        milvus_client: MilvusClient,
    ) -> None:
        """
        Initialize score service.

        Args:
            db_session: Database session
            milvus_client: Milvus vector database client
        """
        self.db = db_session
        self.milvus = milvus_client
        self.pref_config = preference_config

    async def calculate_score(
        self,
        user_id: str,
        entry_id: str,
        entry: Entry | None = None,
    ) -> dict[str, Any]:
        """
        Calculate preference score for an entry in real-time.

        Args:
            user_id: User UUID
            entry_id: Entry UUID
            entry: Optional Entry object (to avoid extra DB query)

        Returns:
            Dictionary with score and factors
        """
        # Get entry embedding from Milvus
        embedding = await self.milvus.get_entry_embedding(entry_id)
        if not embedding:
            # Entry not embedded yet, return default
            return {
                "score": self.pref_config.default_score,
                "factors": {"confidence": 0, "reason": "no_embedding"},
            }

        # Get entry metadata if not provided
        if not entry:
            result = await self.db.execute(select(Entry).where(Entry.id == entry_id))
            entry = result.scalar_one_or_none()
            if not entry:
                return {
                    "score": self.pref_config.default_score,
                    "factors": {"confidence": 0, "reason": "entry_not_found"},
                }

        # Get user preferences
        prefs = await self.milvus.get_user_preferences(user_id)

        if not prefs.get("positive") and not prefs.get("negative"):
            # No preference model yet
            return {
                "score": self.pref_config.default_score,
                "factors": {"confidence": 0, "reason": "no_preference_model"},
            }

        # Calculate similarities
        entry_vec = np.array(embedding)

        positive_sim = 0.0
        negative_sim = 0.0

        if prefs.get("positive"):
            pos_vec = np.array(prefs["positive"]["embedding"])
            positive_sim = float(np.dot(entry_vec, pos_vec))

        if prefs.get("negative"):
            neg_vec = np.array(prefs["negative"]["embedding"])
            negative_sim = float(np.dot(entry_vec, neg_vec))

        # Raw score from similarities [-1, 1]
        raw_score = positive_sim - negative_sim

        # Calculate confidence
        total_samples = 0.0
        if prefs.get("positive"):
            total_samples += prefs["positive"]["sample_count"]
        if prefs.get("negative"):
            total_samples += prefs["negative"]["sample_count"]

        confidence = min(1.0, total_samples / self.pref_config.confidence_threshold)

        # Normalize to [0, 100], low confidence trends toward 50
        base_score = (raw_score + 1) / 2 * 100
        score_with_confidence = base_score * confidence + 50 * (1 - confidence)

        # Get affinity statistics
        result = await self.db.execute(
            select(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
        )
        stats = result.scalar_one_or_none()

        # Apply affinity boosts
        source_boost = 0.0
        author_boost = 0.0

        if stats:
            source_boost = self._calc_affinity_boost(
                stats.source_affinity.get(entry.feed_id, {}),
                self.pref_config.source_boost_max,
            )

            if entry.author:
                author_boost = self._calc_affinity_boost(
                    stats.author_affinity.get(entry.author, {}),
                    self.pref_config.author_boost_max,
                )

        # Final score
        final_score = score_with_confidence + source_boost + author_boost
        final_score = max(0, min(100, final_score))

        return {
            "score": round(final_score, 1),
            "factors": {
                "positive_sim": round(positive_sim, 3),
                "negative_sim": round(negative_sim, 3),
                "confidence": round(confidence, 3),
                "source_boost": round(source_boost, 2),
                "author_boost": round(author_boost, 2),
            },
        }

    def _calc_affinity_boost(self, affinity: dict[str, float], max_boost: float) -> float:
        """
        Calculate affinity boost from positive/negative counts.

        Args:
            affinity: Dictionary with "positive" and "negative" keys
            max_boost: Maximum boost value

        Returns:
            Boost value
        """
        pos = affinity.get("positive", 0)
        neg = affinity.get("negative", 0)
        total = pos + neg

        if total == 0:
            return 0.0

        # Normalize to [-1, 1], then scale to max_boost
        return ((pos - neg) / total) * max_boost

    async def batch_calculate_scores(
        self,
        user_id: str,
        entries: list[Entry],
    ) -> dict[str, float]:
        """
        Calculate preference scores for multiple entries.

        Args:
            user_id: User UUID
            entries: List of Entry objects

        Returns:
            Dictionary mapping entry_id to score
        """
        scores: dict[str, float] = {}

        # Get user preferences once
        prefs = await self.milvus.get_user_preferences(user_id)

        # Get affinity stats once
        result = await self.db.execute(
            select(UserPreferenceStats).where(UserPreferenceStats.user_id == user_id)
        )
        stats = result.scalar_one_or_none()

        # Check if user has preference model
        has_preference = prefs.get("positive") or prefs.get("negative")

        if not has_preference:
            # No preference model, return default scores
            for entry in entries:
                scores[entry.id] = self.pref_config.default_score
            return scores

        # Pre-compute user preference vectors
        pos_vec = None
        neg_vec = None
        total_samples = 0.0

        if prefs.get("positive"):
            pos_vec = np.array(prefs["positive"]["embedding"])
            total_samples += prefs["positive"]["sample_count"]

        if prefs.get("negative"):
            neg_vec = np.array(prefs["negative"]["embedding"])
            total_samples += prefs["negative"]["sample_count"]

        confidence = min(1.0, total_samples / self.pref_config.confidence_threshold)

        # Get all entry embeddings in batch
        entry_ids = [entry.id for entry in entries]
        embeddings = await self.milvus.batch_get_entry_embeddings(entry_ids)

        # Calculate scores
        for entry in entries:
            embedding = embeddings.get(entry.id)

            if not embedding:
                scores[entry.id] = self.pref_config.default_score
                continue

            entry_vec = np.array(embedding)

            # Calculate similarities
            positive_sim = float(np.dot(entry_vec, pos_vec)) if pos_vec is not None else 0.0
            negative_sim = float(np.dot(entry_vec, neg_vec)) if neg_vec is not None else 0.0

            # Raw score from similarities [-1, 1]
            raw_score = positive_sim - negative_sim

            # Normalize to [0, 100], low confidence trends toward 50
            base_score = (raw_score + 1) / 2 * 100
            score_with_confidence = base_score * confidence + 50 * (1 - confidence)

            # Apply affinity boosts
            source_boost = 0.0
            author_boost = 0.0

            if stats:
                source_boost = self._calc_affinity_boost(
                    stats.source_affinity.get(entry.feed_id, {}),
                    self.pref_config.source_boost_max,
                )

                if entry.author:
                    author_boost = self._calc_affinity_boost(
                        stats.author_affinity.get(entry.author, {}),
                        self.pref_config.author_boost_max,
                    )

            # Final score
            final_score = score_with_confidence + source_boost + author_boost
            final_score = max(0, min(100, final_score))

            scores[entry.id] = round(final_score, 1)

        return scores
