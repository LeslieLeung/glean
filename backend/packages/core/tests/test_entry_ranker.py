"""Tests for the Smart scoring and source diversification rules."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from glean_core.services.entry_ranker import EntryRanker, RankedEntry, RankEntry, rank_entries

NOW = datetime(2026, 11, 24, tzinfo=UTC)


def entry(entry_id: str, title: str, reaction: bool | None = None) -> RankEntry:
    return RankEntry(entry_id, "feed", NOW - timedelta(days=3), title, None, reaction)


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
