"""Tests for EmbeddingService transaction handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Entry
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.services.embedding_service import (
    EmbeddingService,
    StaleEmbeddingGenerationError,
)


@pytest.mark.asyncio
async def test_generate_embedding_rolls_back_before_marking_failed() -> None:
    """Roll back a failed transaction and durably commit the failed status."""
    session = AsyncMock(spec=AsyncSession)
    embedding_client = AsyncMock(spec=EmbeddingClient)
    vector_client = AsyncMock()

    entry = MagicMock(spec=Entry)
    entry.id = "entry-1"
    entry.title = "Test entry"
    entry.readability_content = None
    entry.content = "Content to embed"
    entry.summary = None
    entry.embedding_status = "pending"
    entry.feed_id = "feed-1"
    entry.published_at = None
    entry.author = None

    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = entry

    call_count = 0

    async def execute_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return select_result
        if call_count == 2:
            return MagicMock()
        if call_count == 3:
            raise SQLAlchemyError("status update failed")

        assert session.rollback.await_count == 1
        return MagicMock()

    session.execute.side_effect = execute_side_effect
    session.flush = AsyncMock()
    session.rollback = AsyncMock()

    embedding_client.generate_embedding.return_value = ([0.1, 0.2, 0.3], {})
    vector_client.insert_entry_embedding = AsyncMock()

    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
    )

    with pytest.raises(SQLAlchemyError):
        await service.generate_embedding("entry-1")

    session.rollback.assert_awaited_once()
    session.commit.assert_awaited_once()
    assert session.execute.await_count == 4
    assert session.flush.await_count == 2


@pytest.mark.asyncio
async def test_vector_write_checks_generation_inside_rebuild_lock() -> None:
    """A stale job must not write after a collection generation changes."""
    session = AsyncMock(spec=AsyncSession)
    embedding_client = AsyncMock(spec=EmbeddingClient)
    vector_client = AsyncMock()
    generation_guard = AsyncMock(return_value=False)

    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.release = AsyncMock()
    redis = MagicMock()
    redis.lock.return_value = lock

    entry = MagicMock(spec=Entry)
    entry.id = "entry-1"
    entry.feed_id = "feed-1"
    entry.published_at = None
    entry.author = None

    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
        generation_guard=generation_guard,
        generation_lock=redis,
    )

    with pytest.raises(StaleEmbeddingGenerationError):
        await service._store_embedding(
            entry=entry,
            embedding=[0.1, 0.2],
            language="en",
            word_count=2,
        )

    generation_guard.assert_awaited_once()
    vector_client.insert_entry_embedding.assert_not_awaited()
    lock.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_batch_restores_unfinished_claims_to_pending() -> None:
    """A stale generation returns every unfinished processing row to the queue."""
    session = AsyncMock(spec=AsyncSession)
    embedding_client = AsyncMock(spec=EmbeddingClient)
    vector_client = AsyncMock()

    claim_result = MagicMock()
    claim_result.all.return_value = [("entry-1",), ("entry-2",)]
    session.execute.side_effect = [
        claim_result,
        MagicMock(),
        MagicMock(),
    ]

    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
    )
    service.generate_embedding = AsyncMock(side_effect=StaleEmbeddingGenerationError())

    result = await service.batch_generate(limit=2)

    assert result == {"processed": 0, "failed": 0}
    assert session.execute.await_count == 3
    assert session.commit.await_count == 2
    session.rollback.assert_awaited_once()
