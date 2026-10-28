"""Tests for EmbeddingService transaction handling."""

import asyncio
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

    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
    )
    service._claim_entries = AsyncMock(return_value=["entry-1", "entry-2"])  # type: ignore[method-assign]
    service._embed_claimed_entries = AsyncMock(  # type: ignore[method-assign]
        side_effect=StaleEmbeddingGenerationError()
    )
    service.restore_claimed_entries = AsyncMock()  # type: ignore[method-assign]

    result = await service.batch_generate(limit=2, chunk_size=2)

    assert result == {"processed": 0, "failed": 0}
    service._claim_entries.assert_awaited_once()
    service.restore_claimed_entries.assert_awaited_once_with(["entry-1", "entry-2"])
    embedding_client.acquire_rate_limit.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_generate_claims_one_provider_chunk_at_a_time() -> None:
    """Jobs must not mark a 200-entry slice as processing before they can finish it."""
    session = AsyncMock(spec=AsyncSession)
    embedding_client = AsyncMock(spec=EmbeddingClient)
    vector_client = AsyncMock()
    claimed_limits: list[int] = []

    async def claim_entries(*, status: str, limit: int, order_by: object) -> list[str]:
        claimed_limits.append(limit)
        if len(claimed_limits) == 1:
            return ["entry-1", "entry-2"]
        return []

    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
    )
    service._claim_entries = claim_entries  # type: ignore[method-assign]
    service._embed_claimed_entries = AsyncMock(return_value=(2, 0))  # type: ignore[method-assign]

    result = await service.batch_generate(limit=200, chunk_size=2)

    assert result == {"processed": 2, "failed": 0}
    assert claimed_limits == [2, 2]
    assert embedding_client.acquire_rate_limit.await_count == 2


@pytest.mark.asyncio
async def test_batch_generate_stops_before_job_deadline() -> None:
    """A rate-limited job must stop in time to avoid arq's 300s timeout."""
    session = AsyncMock(spec=AsyncSession)
    embedding_client = AsyncMock(spec=EmbeddingClient)
    vector_client = AsyncMock()
    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
    )
    service._claim_entries = AsyncMock(return_value=["entry-1"])  # type: ignore[method-assign]

    result = await service.batch_generate(limit=200, chunk_size=20, deadline=0)

    assert result == {"processed": 0, "failed": 0}
    service._claim_entries.assert_not_awaited()
    embedding_client.acquire_rate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_batch_restores_current_provider_chunk() -> None:
    """arq cancellation must immediately return every in-flight claim to pending."""
    session = AsyncMock(spec=AsyncSession)
    embedding_client = AsyncMock(spec=EmbeddingClient)
    vector_client = AsyncMock()
    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
    )
    service._claim_entries = AsyncMock(return_value=["entry-1", "entry-2"])  # type: ignore[method-assign]
    service._embed_claimed_entries = AsyncMock(  # type: ignore[method-assign]
        side_effect=asyncio.CancelledError()
    )
    service.restore_claimed_entries = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await service.batch_generate(limit=2, chunk_size=2)

    session.rollback.assert_awaited_once()
    service.restore_claimed_entries.assert_awaited_once_with(["entry-1", "entry-2"])


@pytest.mark.asyncio
async def test_batch_generate_uses_provider_batch_api() -> None:
    """Rebuild/idle jobs should consume one RPM slot per provider batch, not per entry."""
    session = AsyncMock(spec=AsyncSession)
    embedding_client = AsyncMock(spec=EmbeddingClient)
    vector_client = AsyncMock()

    entry = MagicMock(spec=Entry)
    entry.id = "entry-1"
    entry.title = "Title"
    entry.content = "Body text"
    entry.summary = None
    entry.embedding_status = "processing"
    entry.feed_id = "feed-1"
    entry.published_at = None
    entry.author = None

    claim_result = MagicMock()
    claim_result.all.return_value = [("entry-1",)]
    load_result = MagicMock()
    load_result.scalars.return_value.all.return_value = [entry]
    session.execute.side_effect = [claim_result, MagicMock(), load_result]

    embedding_client.generate_embeddings_batch_acquired.return_value = ([[0.1, 0.2]], {})

    service = EmbeddingService(
        db_session=session,
        embedding_client=embedding_client,
        vector_client=vector_client,
    )
    service._store_embedding = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service._mark_affected_preferences_pending = AsyncMock()  # type: ignore[method-assign]

    result = await service.batch_generate(limit=1, chunk_size=1)

    assert result == {"processed": 1, "failed": 0}
    embedding_client.generate_embeddings_batch_acquired.assert_awaited_once()
    embedding_client.generate_embedding.assert_not_called()
