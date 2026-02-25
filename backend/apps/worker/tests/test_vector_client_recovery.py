"""Tests for worker vector client recovery behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_worker.tasks._vector_client import ensure_vector_client
from glean_worker.tasks.embedding_worker import validate_and_rebuild_embeddings


def test_ensure_vector_client_reuses_existing_client():
    """Should reuse client already attached to worker context."""
    existing = MagicMock()
    ctx = {"vector_client": existing}

    client, error = ensure_vector_client(ctx)

    assert client is existing
    assert error is None


def test_ensure_vector_client_sets_error_when_connect_fails():
    """Should cache connection error for status reporting."""
    ctx: dict[str, object] = {}

    with patch("glean_worker.tasks._vector_client.create_vector_store_client") as create_client:
        failed_client = MagicMock()
        failed_client.connect.side_effect = RuntimeError("connect failed")
        create_client.return_value = failed_client

        client, error = ensure_vector_client(ctx)

    assert client is None
    assert error == "connect failed"
    assert ctx["vector_client"] is None
    assert ctx["vector_client_error"] == "connect failed"


@pytest.mark.asyncio
async def test_validate_and_rebuild_surfaces_vector_client_error():
    """Should include vector client init error in embedding status and response."""
    ctx = {"redis": AsyncMock()}
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.REBUILDING,
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dimension=384,
    )

    with (
        patch(
            "glean_worker.tasks.embedding_worker.ensure_vector_client",
            return_value=(None, "connect failed"),
        ),
        patch("glean_worker.tasks.embedding_worker.get_session_context") as get_session_context,
        patch("glean_worker.tasks.embedding_worker.TypedConfigService") as config_service_cls,
        patch("glean_vector.services.EmbeddingValidationService") as validation_service_cls,
    ):
        mock_session = AsyncMock()
        get_session_context.return_value.__aenter__.return_value = mock_session

        config_service = AsyncMock()
        config_service.get.return_value = config
        config_service_cls.return_value = config_service

        validation_service = AsyncMock()
        validation_service.validate_provider.return_value = MagicMock(success=True)
        validation_service_cls.return_value = validation_service

        result = await validate_and_rebuild_embeddings(ctx)

    assert result["success"] is False
    assert result["error"] == "Vector client not available: connect failed"
    config_service.set_embedding_status.assert_awaited_once_with(
        VectorizationStatus.ERROR.value,
        error="Vector client not available: connect failed",
    )
