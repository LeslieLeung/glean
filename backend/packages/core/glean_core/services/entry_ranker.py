"""Recommendation scoring shared by Smart lists and the timeline."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from math import hypot, isfinite
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from glean_core import get_logger
from glean_core.schemas.entry import RecommendationReason

logger = get_logger(__name__)
SCORE_BATCH_SIZE = 200
FEEDBACK_LIMIT = 50
GLOBAL_CANDIDATE_LIMIT = 500
GLOBAL_WINDOW_DAYS = 14

_HTML = re.compile(r"<[^>]+>")
_WORD = r"[^\W_\u3400-\u9fff]+"
_TOKEN = re.compile(rf"[\u3400-\u9fff]+|{_WORD}(?:[-_]{_WORD})*")
_HAN = re.compile(r"[\u3400-\u9fff]")
_STOP_WORDS = frozenset(
    [
        "about",
        "article",
        "from",
        "guide",
        "have",
        "news",
        "that",
        "their",
        "this",
        "tutorial",
        "update",
        "what",
        "when",
        "where",
        "with",
        "your",
        "教程",
        "更新",
        "文章",
        "新鲜",
        "新闻",
        "一个",
        "如何",
        "进行",
        "内容",
        "我们",
        "他们",
        "可以",
        "这个",
    ]
)


class EmbeddingReader(Protocol):
    async def batch_get_entry_embeddings(self, entry_ids: list[str]) -> dict[str, list[float]]: ...


@dataclass(frozen=True)
class RankEntry:
    id: str
    feed_id: str
    published_at: datetime
    title: str
    summary: str | None
    reaction: bool | None


@dataclass(frozen=True)
class RankedEntry:
    id: str
    feed_id: str
    published_at: datetime
    score: float
    reason: RecommendationReason


def _terms(entry: RankEntry) -> dict[str, float]:
    terms: Counter[str] = Counter()
    for raw_text, weight in ((entry.title, 3), (entry.summary or "", 1)):
        text = unicodedata.normalize("NFKC", _HTML.sub(" ", unescape(raw_text[:4000]))).casefold()
        # Each term contributes at most once per field.
        field_terms: set[str] = set()
        for token in _TOKEN.findall(text):
            if _HAN.match(token):
                field_terms.update(token[i : i + 2] for i in range(len(token) - 1))
            elif len(token) >= 3:
                field_terms.add(token)
        terms.update(dict.fromkeys(field_terms - _STOP_WORDS, weight))
    norm = hypot(*terms.values())
    return {key: value / norm for key, value in terms.items()}


def _unit_vector(vector: list[float]) -> tuple[float, ...]:
    norm = hypot(*vector)
    if not norm or not isfinite(norm):
        return ()
    return tuple(value / norm for value in vector)


def _match_strength(similarity: float, low: float, high: float) -> float:
    return min(1.0, max(0.0, (similarity - low) / (high - low)))


class EntryRanker:
    """Score a batch against one fixed set of feedback and one request clock."""

    def __init__(
        self, now: datetime, feedback: list[RankEntry], embeddings: EmbeddingReader | None = None
    ) -> None:
        self.now = now
        self.feedback = [(entry, _terms(entry)) for entry in feedback]
        self.embeddings = embeddings
        self.feedback_vectors: dict[int, tuple[list[str], NDArray[np.float32]]] = {}

    async def load_feedback_vectors(self) -> None:
        vectors = await self._vectors([sample.id for sample, _ in self.feedback])
        for dimension, rows in _by_dimension(vectors).items():
            self.feedback_vectors[dimension] = (
                [entry_id for entry_id, _ in rows],
                np.asarray([vector for _, vector in rows], dtype=np.float32),
            )

    async def _vectors(self, ids: list[str]) -> dict[str, tuple[float, ...]]:
        if self.embeddings is None or not ids:
            return {}
        try:
            vectors = await self.embeddings.batch_get_entry_embeddings(ids)
        except Exception:
            logger.warning(
                "Smart ranking fell back to text matching after a vector read failed", exc_info=True
            )
            self.embeddings = None
            return {}
        return {entry_id: _unit_vector(vector) for entry_id, vector in vectors.items()}

    async def score(self, entries: list[RankEntry]) -> list[RankedEntry]:
        vectors = (
            await self._vectors([entry.id for entry in entries if entry.reaction is None])
            if self.feedback_vectors
            else {}
        )
        similarities: dict[str, dict[str, float]] = {}
        for dimension, rows in _by_dimension(vectors).items():
            feedback = self.feedback_vectors.get(dimension)
            if feedback is None:
                continue
            sample_ids, profile = feedback
            candidates = np.asarray([vector for _, vector in rows], dtype=np.float32)
            for (entry_id, _), scores in zip(rows, candidates @ profile.T, strict=True):
                similarities[entry_id] = dict(zip(sample_ids, scores.tolist(), strict=True))
        return [self._score(entry, similarities.get(entry.id, {})) for entry in entries]

    def _score(self, entry: RankEntry, similarities: dict[str, float]) -> RankedEntry:
        age_days = max(0.0, (self.now - entry.published_at).total_seconds() / 86400)
        base = 25 + 65 * 2 ** (-age_days / 3)
        reason: RecommendationReason = "publication"
        if entry.reaction is not None:
            adjustment = 20 if entry.reaction else -20
            reason = "liked" if entry.reaction else "disliked"
        else:
            adjustment = self._interest_adjustment(entry, similarities)
            if adjustment > 0:
                reason = "similar_liked"
            elif adjustment < 0:
                reason = "similar_disliked"
        score = min(100.0, max(0.0, base + adjustment))
        return RankedEntry(entry.id, entry.feed_id, entry.published_at, score, reason)

    def _interest_adjustment(self, entry: RankEntry, similarities: dict[str, float]) -> float:
        if not self.feedback:
            return 0.0
        positive: list[float] = []
        negative: list[float] = []
        terms: dict[str, float] | None = None
        for sample, sample_terms in self.feedback:
            if sample.id == entry.id or sample.reaction is None:
                continue
            similarity = similarities.get(sample.id)
            if similarity is not None:
                low, high = (0.55, 0.85) if sample.reaction else (0.68, 0.92)
            else:
                if terms is None:
                    terms = _terms(entry)
                similarity = sum(
                    terms[term] * sample_terms[term] for term in terms.keys() & sample_terms.keys()
                )
                low, high = (0.18, 0.7) if sample.reaction else (0.4, 0.85)
            strength = _match_strength(similarity, low, high)
            (positive if sample.reaction else negative).append(strength)
        return 20 * (_evidence(positive) - _evidence(negative))


def _by_dimension(
    vectors: dict[str, tuple[float, ...]],
) -> dict[int, list[tuple[str, tuple[float, ...]]]]:
    groups: dict[int, list[tuple[str, tuple[float, ...]]]] = defaultdict(list)
    for entry_id, vector in vectors.items():
        if vector:
            groups[len(vector)].append((entry_id, vector))
    return groups


def _evidence(matches: list[float]) -> float:
    return sum(
        weight * value
        for weight, value in zip((0.7, 0.3), sorted(matches, reverse=True)[:2], strict=False)
    )


def rank_entries(entries: list[RankedEntry], *, diversify: bool) -> list[RankedEntry]:
    ordered = sorted(
        entries, key=lambda entry: (-entry.score, -entry.published_at.timestamp(), entry.id)
    )
    if diversify:
        for index in range(2, len(ordered)):
            current = ordered[index]
            if all(previous.feed_id == current.feed_id for previous in ordered[index - 2 : index]):
                for alternative in range(index + 1, min(index + 6, len(ordered))):
                    candidate = ordered[alternative]
                    if current.score - candidate.score > 5:
                        break
                    if candidate.feed_id != current.feed_id:
                        ordered.insert(index, ordered.pop(alternative))
                        break
    return ordered
