"""Tests for worker vector client recovery behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry

from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)
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
        status=VectorizationStatus.VALIDATING,
        version="version-1",
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dimension=384,
        target_vector_backend=vector_backend_config.backend,
        target_vector_store_fingerprint=vector_store_fingerprint(),
        target_model_fingerprint=embedding_model_fingerprint(
            "sentence-transformers",
            "all-MiniLM-L6-v2",
            384,
            None,
        ),
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
        mock_session.expire_all = MagicMock()
        get_session_context.return_value.__aenter__.return_value = mock_session

        config_service = AsyncMock()
        config_service.get.return_value = config
        config_service_cls.return_value = config_service

        validation_service = AsyncMock()
        validation_service.validate_provider.return_value = MagicMock(success=True)
        validation_service_cls.return_value = validation_service

        result = await validate_and_rebuild_embeddings(
            ctx,
            expected_version="version-1",
        )

    assert result["success"] is False
    assert result["error"] == "Vector client not available: connect failed"
    assert config_service.update_embedding_generation.await_count == 1
    assert (
        config_service.update_embedding_generation.await_args.kwargs["status"]
        == VectorizationStatus.ERROR
    )


@pytest.mark.asyncio
async def test_backend_identity_change_forces_rebuild_even_when_storage_is_compatible():
    """Switching Milvus -> pgvector must not adopt an empty compatible backend."""
    redis = AsyncMock()
    ctx = {"redis": redis}
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.VALIDATING,
        version="version-1",
        vector_backend="milvus",
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dimension=384,
        target_vector_backend="pgvector",
        target_vector_store_fingerprint="store-new",
        target_model_fingerprint=embedding_model_fingerprint(
            "sentence-transformers",
            "all-MiniLM-L6-v2",
            384,
            None,
        ),
    )
    vector_client = MagicMock()
    backend_result = MagicMock(
        success=True,
        details={"is_compatible": True, "collections_exist": True},
    )

    with (
        patch(
            "glean_worker.tasks.embedding_worker.ensure_vector_client",
            return_value=(vector_client, None),
        ),
        patch("glean_worker.tasks.embedding_worker.get_session_context") as session_context,
        patch("glean_worker.tasks.embedding_worker.TypedConfigService") as config_service_cls,
        patch("glean_vector.services.EmbeddingValidationService") as validation_service_cls,
        patch(
            "glean_worker.tasks.embedding_worker.vector_backend_config.backend",
            "pgvector",
        ),
        patch(
            "glean_worker.tasks.embedding_worker.vector_store_fingerprint",
            return_value="store-new",
        ),
    ):
        mock_session = AsyncMock()
        mock_session.expire_all = MagicMock()
        session_context.return_value.__aenter__.return_value = mock_session
        config_service = AsyncMock()
        config_service.get.return_value = config
        config_service_cls.return_value = config_service
        validation_service = AsyncMock()
        validation_service.validate_provider.return_value = MagicMock(success=True)
        validation_service.validate_vector_backend.return_value = backend_result
        validation_service_cls.return_value = validation_service

        result = await validate_and_rebuild_embeddings(
            ctx,
            expected_version="version-1",
        )

    assert result["success"] is True
    assert "rebuild queued" in result["message"].lower()
    redis.enqueue_job.assert_awaited_once_with(
        "rebuild_embeddings",
        expected_version="version-1",
        expected_backend="pgvector",
        expected_store_fingerprint="store-new",
        expected_model_fingerprint=config.target_model_fingerprint,
        _job_id="rebuild_version-1",
    )


@pytest.mark.asyncio
async def test_legacy_milvus_identity_is_adopted_without_destructive_rebuild():
    """Unsigned legacy Milvus storage remains compatible and is adopted."""
    redis = AsyncMock()
    ctx = {"redis": redis}
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.VALIDATING,
        version="version-1",
        vector_backend=None,
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dimension=384,
        target_vector_backend="milvus",
        target_vector_store_fingerprint="store-legacy",
        target_model_fingerprint=embedding_model_fingerprint(
            "sentence-transformers",
            "all-MiniLM-L6-v2",
            384,
            None,
        ),
    )
    vector_client = MagicMock()
    backend_result = MagicMock(
        success=True,
        details={"is_compatible": True, "collections_exist": True},
    )

    with (
        patch(
            "glean_worker.tasks.embedding_worker.ensure_vector_client",
            return_value=(vector_client, None),
        ),
        patch("glean_worker.tasks.embedding_worker.get_session_context") as session_context,
        patch("glean_worker.tasks.embedding_worker.TypedConfigService") as config_service_cls,
        patch("glean_vector.services.EmbeddingValidationService") as validation_service_cls,
        patch(
            "glean_worker.tasks.embedding_worker.vector_backend_config.backend",
            "milvus",
        ),
        patch(
            "glean_worker.tasks.embedding_worker.vector_store_fingerprint",
            return_value="store-legacy",
        ),
    ):
        mock_session = AsyncMock()
        mock_session.expire_all = MagicMock()
        session_context.return_value.__aenter__.return_value = mock_session
        config_service = AsyncMock()
        config_service.get.return_value = config
        config_service_cls.return_value = config_service
        validation_service = AsyncMock()
        validation_service.validate_provider.return_value = MagicMock(success=True)
        validation_service.validate_vector_backend.return_value = backend_result
        validation_service_cls.return_value = validation_service

        result = await validate_and_rebuild_embeddings(
            ctx,
            expected_version="version-1",
        )

    assert result["skipped_rebuild"] is True
    assert config_service.update_embedding_generation.await_count == 1
    update_kwargs = config_service.update_embedding_generation.await_args.kwargs
    assert update_kwargs["status"] == VectorizationStatus.IDLE
    assert update_kwargs["vector_backend"] == "milvus"
    assert update_kwargs["vector_store_fingerprint"] == "store-legacy"
    assert update_kwargs["target_vector_backend"] is None
    redis.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_validation_without_payload_still_honors_persisted_target():
    """An old-format queued job cannot make the wrong replica touch its store."""
    other_backend = "milvus" if vector_backend_config.backend == "pgvector" else "pgvector"
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.VALIDATING,
        version="version-1",
        target_vector_backend=other_backend,
        target_vector_store_fingerprint="other-store",
        target_model_fingerprint=embedding_model_fingerprint(
            "sentence-transformers",
            "all-MiniLM-L6-v2",
            384,
            None,
        ),
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dimension=384,
    )
    context = MagicMock()
    session = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    config_service = AsyncMock()
    config_service.get.return_value = config

    with (
        patch(
            "glean_worker.tasks.embedding_worker.get_session_context",
            return_value=context,
        ),
        patch(
            "glean_worker.tasks.embedding_worker.TypedConfigService",
            return_value=config_service,
        ),
        patch(
            "glean_worker.tasks.embedding_worker.ensure_vector_client",
        ) as ensure_client,
        pytest.raises(Retry),
    ):
        await validate_and_rebuild_embeddings({"redis": AsyncMock()})

    ensure_client.assert_not_called()
