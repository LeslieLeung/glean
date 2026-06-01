"""Tests for EmbeddingService transaction handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Entry
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.services.embedding_service import EmbeddingService


@pytest.mark.asyncio
async def test_generate_embedding_rolls_back_before_marking_failed() -> None:
    """Roll back a failed DB transaction before writing the failed status."""
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
    assert session.execute.await_count == 4
    assert session.flush.await_count == 2
