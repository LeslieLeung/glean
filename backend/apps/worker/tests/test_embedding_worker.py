"""Tests for single-entry embedding retry and circuit-breaker behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_worker.tasks.embedding_worker import (
    _safe_handle_error,
    generate_entry_embedding,
)


def _embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.IDLE,
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dimension=384,
    )


def _session_context(session: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


@pytest.mark.asyncio
async def test_safe_handle_error_commits_circuit_breaker_update() -> None:
    """A subsequent Retry must not roll back the global failure count."""
    session = AsyncMock(spec=AsyncSession)
    error = RuntimeError("backend unavailable")

    with patch(
        "glean_worker.tasks.embedding_worker._handle_embedding_error",
        new=AsyncMock(return_value=2),
    ) as handle_error:
        failure_count = await _safe_handle_error(
            session,
            error,
            expected_version="version-1",
            expected_rebuild_id=None,
        )

    assert failure_count == 2
    session.rollback.assert_awaited_once()
    handle_error.assert_awaited_once_with(
        session,
        error,
        expected_version="version-1",
        expected_rebuild_id=None,
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_entry_embedding_retries_transient_failure_with_backoff() -> None:
    """Infrastructure errors are retried after their failed status is committed."""
    session = AsyncMock(spec=AsyncSession)
    vector_client = AsyncMock()
    embedding_client = AsyncMock()
    service = AsyncMock()
    service.generate_embedding.side_effect = RuntimeError("Milvus unavailable")

    with (
        patch(
            "glean_worker.tasks.embedding_worker.get_session_context",
            return_value=_session_context(session),
        ),
        patch(
            "glean_worker.tasks.embedding_worker._check_vectorization_enabled",
            new=AsyncMock(return_value=(True, _embedding_config())),
        ),
        patch(
            "glean_worker.tasks.embedding_worker.EmbeddingClient",
            return_value=embedding_client,
        ),
        patch(
            "glean_worker.tasks.embedding_worker.EmbeddingService",
            return_value=service,
        ),
        patch(
            "glean_worker.tasks.embedding_worker._safe_handle_error",
            new=AsyncMock(return_value=2),
        ),
        pytest.raises(Retry) as exc_info,
    ):
        await generate_entry_embedding(
            {"vector_client": vector_client, "job_try": 2},
            "entry-1",
        )

    assert exc_info.value.defer_score == 120_000
    embedding_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_entry_embedding_stops_retry_when_circuit_opens() -> None:
    """The fifth global failure opens the circuit instead of creating a retry storm."""
    session = AsyncMock(spec=AsyncSession)
    vector_client = AsyncMock()
    embedding_client = AsyncMock()
    service = AsyncMock()
    service.generate_embedding.side_effect = RuntimeError("Milvus unavailable")

    with (
        patch(
            "glean_worker.tasks.embedding_worker.get_session_context",
            return_value=_session_context(session),
        ),
        patch(
            "glean_worker.tasks.embedding_worker._check_vectorization_enabled",
            new=AsyncMock(return_value=(True, _embedding_config())),
        ),
        patch(
            "glean_worker.tasks.embedding_worker.EmbeddingClient",
            return_value=embedding_client,
        ),
        patch(
            "glean_worker.tasks.embedding_worker.EmbeddingService",
            return_value=service,
        ),
        patch(
            "glean_worker.tasks.embedding_worker._safe_handle_error",
            new=AsyncMock(return_value=5),
        ),
    ):
        result = await generate_entry_embedding(
            {"vector_client": vector_client, "job_try": 1},
            "entry-1",
        )

    assert result == {
        "success": False,
        "entry_id": "entry-1",
        "error": "Milvus unavailable",
    }
    embedding_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_entry_embedding_retries_initial_connection_failure() -> None:
    """A client initialization outage is retried without a tight loop."""
    with (
        patch(
            "glean_worker.tasks.embedding_worker.ensure_vector_client",
            return_value=(None, "connection refused"),
        ),
        pytest.raises(Retry) as exc_info,
    ):
        await generate_entry_embedding({"job_try": 3}, "entry-1")

    assert exc_info.value.defer_score == 240_000
