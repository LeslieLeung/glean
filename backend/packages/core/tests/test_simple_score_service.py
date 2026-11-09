"""Unit tests for non-vector Smart view scoring."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from glean_core.services.simple_score_service import SimpleScoreService
from glean_database.models import Entry

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        if tz is None:
            return NOW.replace(tzinfo=None)
        return NOW.astimezone(tz)


def _service(stats: SimpleNamespace | None = None) -> SimpleScoreService:
    result = SimpleNamespace(scalar_one_or_none=lambda: stats)
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    return SimpleScoreService(cast(Any, session))


def _entry(
    *,
    entry_id: str = "entry-1",
    published_at: datetime | None = None,
    created_at: datetime | None = None,
    feed_id: str = "feed-1",
    author: str | None = None,
) -> Entry:
    return cast(
        Entry,
        SimpleNamespace(
            id=entry_id,
            published_at=published_at if published_at is not None else NOW - timedelta(hours=12),
            created_at=created_at or NOW,
            feed_id=feed_id,
            author=author,
        ),
    )


def test_recency_decays_from_fresh_to_old() -> None:
    service = _service()

    with patch("glean_core.services.simple_score_service.datetime", _FrozenDateTime):
        assert service._calculate_recency_factor(None) == 0.5
        assert service._calculate_recency_factor(NOW - timedelta(hours=12)) == 1.0
        assert service._calculate_recency_factor(NOW + timedelta(minutes=10)) == 1.0
        assert service._calculate_recency_factor(NOW - timedelta(hours=96)) == 0.75
        assert service._calculate_recency_factor(NOW - timedelta(days=30)) == pytest.approx(0.04)
        assert service._calculate_recency_factor(NOW - timedelta(days=1000)) == 0.0
        assert (
            service._calculate_recency_factor(NOW.replace(tzinfo=None) - timedelta(hours=12)) == 1.0
        )


def test_affinity_uses_smoothed_ratios_and_stays_neutral_without_history() -> None:
    service = _service()
    stats = SimpleNamespace(
        source_affinity={
            "feed-1": {"positive": 8, "negative": 1},
            "quiet": {"positive": 0, "negative": 0},
        },
        author_affinity={"Ada": {"positive": 3, "negative": 0}},
        positive_count=4.0,
        negative_count=1.0,
    )

    assert service._get_source_affinity(None, "feed-1") == 0.5
    assert service._get_source_affinity(cast(Any, stats), "unseen") == 0.5
    assert service._get_source_affinity(cast(Any, stats), "quiet") == 0.5
    assert service._get_source_affinity(cast(Any, stats), "feed-1") == 9 / 11
    assert service._get_author_affinity(cast(Any, stats), None) == 0.5
    assert service._get_author_affinity(cast(Any, stats), "Unknown") == 0.5
    assert service._get_author_affinity(cast(Any, stats), "Ada") == 4 / 5


async def test_far_future_feed_date_scores_from_the_original_fetch_time() -> None:
    service = _service()
    entry = _entry(
        published_at=NOW + timedelta(days=400),
        created_at=NOW - timedelta(days=30),
    )

    with patch("glean_core.services.simple_score_service.datetime", _FrozenDateTime):
        result = await service.calculate_score("user-1", entry)

    assert result["factors"]["recency"] == 0.04
    assert result["factors"]["method"] == "simple"
    assert result["score"] == pytest.approx(33.9)


async def test_missing_feed_date_scores_as_fresh_when_just_fetched() -> None:
    service = _service()
    entry = cast(
        Entry,
        SimpleNamespace(
            id="undated",
            published_at=None,
            created_at=NOW - timedelta(hours=2),
            feed_id="feed-1",
            author=None,
        ),
    )

    with patch("glean_core.services.simple_score_service.datetime", _FrozenDateTime):
        result = await service.calculate_score("user-1", entry)

    assert result["factors"]["recency"] == 1.0
    assert result["score"] == 67.5


async def test_known_source_and_author_raise_the_score() -> None:
    stats = SimpleNamespace(
        source_affinity={"feed-1": {"positive": 8, "negative": 1}},
        author_affinity={"Ada": {"positive": 3, "negative": 0}},
        positive_count=4.0,
        negative_count=1.0,
    )
    service = _service(stats)
    entry = _entry(author="Ada")

    with patch("glean_core.services.simple_score_service.datetime", _FrozenDateTime):
        result = await service.calculate_score("user-1", entry)

    assert result["factors"]["source_affinity"] == round(9 / 11, 3)
    assert result["factors"]["author_affinity"] == round(4 / 5, 3)
    assert result["factors"]["recency"] == 1.0
    assert 67.5 < result["score"] <= 100


async def test_batch_scores_reuse_one_stats_lookup() -> None:
    service = _service()
    entries = [_entry(entry_id="a"), _entry(entry_id="b", feed_id="feed-2")]

    with patch("glean_core.services.simple_score_service.datetime", _FrozenDateTime):
        results = await service.batch_calculate_scores("user-1", entries)

    assert set(results) == {"a", "b"}
    assert service.session.execute.await_count == 1


async def test_recommendation_summary_reports_missing_and_existing_signals() -> None:
    empty = _service()
    assert await empty.get_recommendation_summary("user-1") == {
        "has_data": False,
        "message": "No preference data yet. Like or bookmark articles to improve recommendations.",
    }

    stats = SimpleNamespace(
        source_affinity={"feed-1": {"positive": 1, "negative": 0}},
        author_affinity={},
        positive_count=4.0,
        negative_count=1.0,
    )
    summary = await _service(stats).get_recommendation_summary("user-1")

    assert summary["has_data"] is True
    assert summary["total_signals"] == 5.0
    assert summary["positive_ratio"] == 0.8
    assert summary["top_sources_count"] == 1
    assert summary["top_authors_count"] == 0
    assert summary["method"] == "simple"
