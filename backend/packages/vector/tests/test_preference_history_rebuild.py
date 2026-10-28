"""Tests for idempotent preference reconstruction from durable history."""

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from glean_vector.clients.vector_store import VectorStoreClient
from glean_vector.services.preference_service import (
    PreferenceEmbeddingsNotReadyError,
    PreferenceService,
)


def _result(*, rows=None, scalar=None):
    result = MagicMock()
    result.all.return_value = rows or []
    result.scalar_one_or_none.return_value = scalar
    return result


@pytest.mark.asyncio
async def test_history_rebuild_combines_reactions_and_bookmarks_idempotently():
    session = AsyncMock(spec=AsyncSession)
    vector_client = MagicMock(spec=VectorStoreClient)
    vector_client.batch_get_entry_embeddings = AsyncMock(
        return_value={
            "liked": [1.0, 0.0],
            "disliked": [0.0, 1.0],
            "bookmarked": [1.0, 1.0],
        }
    )
    vector_client.delete_user_preferences = AsyncMock()
    vector_client.upsert_user_preference = AsyncMock()

    liked = MagicMock(id="liked", feed_id="feed-a", author="Alice", embedding_status="done")
    disliked = MagicMock(id="disliked", feed_id="feed-b", author="Bob", embedding_status="done")
    bookmarked = MagicMock(
        id="bookmarked", feed_id="feed-a", author="Alice", embedding_status="done"
    )
    liked_state = MagicMock(is_liked=True)
    disliked_state = MagicMock(is_liked=False)

    session.execute.side_effect = [
        _result(rows=[(liked_state, liked), (disliked_state, disliked)]),
        _result(rows=[(MagicMock(), bookmarked)]),
        _result(scalar=None),
    ]

    service = PreferenceService(session, vector_client)
    await service.rebuild_from_history("user-1")

    vector_client.delete_user_preferences.assert_awaited_once_with("user-1")
    calls = {
        call.kwargs["vector_type"]: call.kwargs
        for call in vector_client.upsert_user_preference.await_args_list
    }
    assert calls["positive"]["sample_count"] == pytest.approx(1.7)
    assert calls["negative"]["sample_count"] == pytest.approx(1.0)
    assert np.linalg.norm(calls["positive"]["embedding"]) == pytest.approx(1.0)
    assert np.linalg.norm(calls["negative"]["embedding"]) == pytest.approx(1.0)

    stats = session.add.call_args.args[0]
    assert stats.positive_count == pytest.approx(1.7)
    assert stats.negative_count == pytest.approx(1.0)
    assert stats.source_affinity["feed-a"]["positive"] == pytest.approx(1.7)
    assert stats.author_affinity["Alice"]["positive"] == pytest.approx(1.7)


@pytest.mark.asyncio
async def test_history_rebuild_does_not_clear_model_before_embeddings_are_ready():
    session = AsyncMock(spec=AsyncSession)
    vector_client = MagicMock(spec=VectorStoreClient)
    vector_client.batch_get_entry_embeddings = AsyncMock(return_value={})
    vector_client.delete_user_preferences = AsyncMock()

    entry = MagicMock(id="pending", feed_id="feed-a", author=None, embedding_status="pending")
    session.execute.side_effect = [
        _result(rows=[(MagicMock(is_liked=True), entry)]),
        _result(rows=[]),
    ]

    service = PreferenceService(session, vector_client)
    with pytest.raises(PreferenceEmbeddingsNotReadyError) as error:
        await service.rebuild_from_history("user-1")

    assert error.value.entry_ids == ["pending"]
    vector_client.delete_user_preferences.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_rebuild_skips_terminal_failed_embeddings():
    session = AsyncMock(spec=AsyncSession)
    vector_client = MagicMock(spec=VectorStoreClient)
    vector_client.batch_get_entry_embeddings = AsyncMock(return_value={})
    vector_client.delete_user_preferences = AsyncMock()
    vector_client.upsert_user_preference = AsyncMock()

    entry = MagicMock(id="failed", feed_id="feed-a", author=None, embedding_status="failed")
    session.execute.side_effect = [
        _result(rows=[(MagicMock(is_liked=True), entry)]),
        _result(rows=[]),
        _result(scalar=None),
    ]

    service = PreferenceService(session, vector_client)
    await service.rebuild_from_history("user-1", allow_failed_embeddings=True)

    vector_client.delete_user_preferences.assert_awaited_once_with("user-1")
    vector_client.upsert_user_preference.assert_not_awaited()
