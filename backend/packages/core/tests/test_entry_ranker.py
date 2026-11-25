"""Tests for the Smart scoring and source diversification rules."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from glean_core.services.entry_ranker import (
    AD_SCORE_PENALTY,
    EntryRanker,
    RankedEntry,
    RankEntry,
    rank_entries,
)

NOW = datetime(2026, 11, 24, tzinfo=UTC)


def entry(
    entry_id: str,
    title: str,
    reaction: bool | None = None,
    *,
    advertisement: bool = False,
) -> RankEntry:
    return RankEntry(
        entry_id, "feed", NOW - timedelta(days=3), title, None, reaction, advertisement
    )


async def test_missing_vector_uses_text_for_that_pair_only() -> None:
    sample = entry("sample", "ESP-IDF配网教程", True)
    related = entry("related", "ESP-IDF配网")
    semantic = entry("semantic", "Wireless onboarding")
    unrelated = entry("unrelated", "Database 文章更新")
    reader = AsyncMock()
    reader.batch_get_entry_embeddings.side_effect = [
        {"sample": [1.0, 0.0]},
        {"semantic": [1.0, 0.0], "unrelated": [0.0, 1.0]},
    ]
    ranker = EntryRanker(NOW, [sample], reader)
    await ranker.load_feedback_vectors()
    results = await ranker.score([related, semantic, unrelated])

    assert [item.reason for item in results] == ["similar_liked", "similar_liked", "publication"]
    assert [item.score for item in results] == pytest.approx([71.5, 71.5, 57.5])


async def test_vector_read_failure_falls_back_to_text() -> None:
    article = entry("candidate", "pgvector indexing")
    sample = entry("sample", "pgvector indexing", False)
    reader = AsyncMock()
    reader.batch_get_entry_embeddings.side_effect = [
        {"sample": [1.0, 0.0]},
        ConnectionError("unavailable"),
    ]
    ranker = EntryRanker(NOW, [sample], reader)
    await ranker.load_feedback_vectors()
    (result,) = await ranker.score([article])

    assert result.score == pytest.approx(43.5)
    assert result.reason == "similar_disliked"


async def test_advertisement_loses_forty_points_and_explains_the_drop() -> None:
    article = entry("article", "Launch notes")
    ad = entry("ad", "Launch notes", advertisement=True)
    results = await EntryRanker(NOW, []).score([article, ad])

    assert results[0].score - results[1].score == pytest.approx(AD_SCORE_PENALTY)
    assert [item.reason for item in results] == ["publication", "advertisement"]
    assert results[1].score > 0


async def test_liked_advertisement_keeps_the_like_reason() -> None:
    liked = entry("liked", "Launch notes", True)
    liked_ad = entry("liked-ad", "Launch notes", True, advertisement=True)
    results = await EntryRanker(NOW, []).score([liked, liked_ad])

    assert results[0].score - results[1].score == pytest.approx(AD_SCORE_PENALTY)
    assert [item.reason for item in results] == ["liked", "liked"]


def test_global_diversification_promotes_only_nearby_alternatives() -> None:
    candidates = [
        RankedEntry("a", "same", NOW, 90, "publication"),
        RankedEntry("b", "same", NOW, 89, "publication"),
        RankedEntry("c", "same", NOW, 87, "publication"),
        RankedEntry("d", "different", NOW, 85, "publication"),
        RankedEntry("e", "same", NOW, 83, "publication"),
        RankedEntry("f", "same", NOW, 82, "publication"),
        RankedEntry("g", "other", NOW, 60, "publication"),
    ]
    assert [item.id for item in rank_entries(candidates, diversify=False)] == list("abcdefg")
    assert [item.id for item in rank_entries(candidates, diversify=True)] == list("abdcefg")
