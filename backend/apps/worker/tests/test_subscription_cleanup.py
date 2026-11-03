"""Tests for subscription vector cleanup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry

from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)
from glean_worker.tasks.subscription_cleanup import cleanup_orphan_embeddings


def _embedding_config() -> EmbeddingConfig:
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.IDLE,
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dimension=384,
        vector_backend=vector_backend_config.backend,
        vector_store_fingerprint=vector_store_fingerprint(),
    )
    return config.model_copy(
        update={
            "model_fingerprint": embedding_model_fingerprint(
                config.provider,
                config.model,
                config.dimension,
                config.base_url,
            )
        }
    )


def _cleanup_dependencies() -> tuple[AsyncMock, MagicMock, AsyncMock]:
    session = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    config_service = AsyncMock()
    config_service.get.return_value = _embedding_config()
    return session, context, config_service


@pytest.mark.asyncio
async def test_cleanup_ensures_storage_before_first_milvus_delete() -> None:
    """A fresh worker initializes Milvus collections before deleting entries."""
    vector_client = AsyncMock()
    _, context, config_service = _cleanup_dependencies()

    with (
        patch(
            "glean_worker.tasks.subscription_cleanup.get_session_context",
            return_value=context,
        ),
        patch(
            "glean_worker.tasks.subscription_cleanup.TypedConfigService",
            return_value=config_service,
        ),
    ):
        result = await cleanup_orphan_embeddings(
            {"vector_client": vector_client},
            "feed-1",
            ["entry-1"],
        )

    vector_client.ensure_collections.assert_awaited_once_with(
        384,
        "sentence-transformers",
        "all-MiniLM-L6-v2",
    )
    vector_client.delete_entry_embedding.assert_awaited_once_with("entry-1")
    assert result["success"] is True
    assert result["deleted"] == 1


@pytest.mark.asyncio
async def test_cleanup_reports_initialization_failure() -> None:
    """Collection initialization failures must not be reported as success."""
    vector_client = AsyncMock()
    vector_client.ensure_collections.side_effect = RuntimeError("Milvus unavailable")
    _, context, config_service = _cleanup_dependencies()

    with (
        patch(
            "glean_worker.tasks.subscription_cleanup.get_session_context",
            return_value=context,
        ),
        patch(
            "glean_worker.tasks.subscription_cleanup.TypedConfigService",
            return_value=config_service,
        ),
        pytest.raises(Retry),
    ):
        await cleanup_orphan_embeddings(
            {"vector_client": vector_client},
            "feed-1",
            ["entry-1", "entry-2"],
        )

    vector_client.delete_entry_embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_reports_partial_delete_failure() -> None:
    """Any failed entry deletion makes the task result unsuccessful."""
    vector_client = AsyncMock()
    vector_client.delete_entry_embedding.side_effect = [
        None,
        RuntimeError("delete failed"),
    ]
    _, context, config_service = _cleanup_dependencies()

    with (
        patch(
            "glean_worker.tasks.subscription_cleanup.get_session_context",
            return_value=context,
        ),
        patch(
            "glean_worker.tasks.subscription_cleanup.TypedConfigService",
            return_value=config_service,
        ),
        pytest.raises(Retry),
    ):
        await cleanup_orphan_embeddings(
            {"vector_client": vector_client},
            "feed-1",
            ["entry-1", "entry-2"],
        )

    assert vector_client.delete_entry_embedding.await_count == 2
