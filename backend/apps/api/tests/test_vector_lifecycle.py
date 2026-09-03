"""API vector-backend reconciliation regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glean_api.vector_lifecycle import reconcile_vector_backend
from glean_core.schemas.config import (
    EmbeddingConfig,
    ValidationResult,
    VectorizationStatus,
)
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)


def _active_config(*, status: VectorizationStatus) -> EmbeddingConfig:
    config = EmbeddingConfig(
        enabled=True,
        status=status,
        version="version-1",
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


@pytest.mark.asyncio
async def test_read_only_backend_failure_leaves_idle_before_ensure() -> None:
    config = _active_config(status=VectorizationStatus.IDLE)
    updated = config.model_copy(
        update={
            "status": VectorizationStatus.VALIDATING,
            "version": "version-2",
            "target_vector_backend": vector_backend_config.backend,
            "target_vector_store_fingerprint": vector_store_fingerprint(),
            "target_model_fingerprint": config.model_fingerprint,
        }
    )
    config_service = AsyncMock()
    config_service.get.return_value = config
    config_service.update_embedding_generation.return_value = updated
    validation_service = AsyncMock()
    validation_service.validate_vector_backend.return_value = ValidationResult(
        success=False,
        message="connection refused",
    )
    redis = AsyncMock()
    app = SimpleNamespace(state=SimpleNamespace(redis_pool=redis))
    session = AsyncMock()
    session.scalar.return_value = 3

    with (
        patch(
            "glean_api.vector_lifecycle.TypedConfigService",
            return_value=config_service,
        ),
        patch(
            "glean_vector.services.EmbeddingValidationService",
            return_value=validation_service,
        ),
    ):
        result = await reconcile_vector_backend(app, session)

    assert result.status == VectorizationStatus.VALIDATING
    config_service.update_embedding_generation.assert_awaited_once()
    redis.enqueue_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_old_replica_does_not_overwrite_another_validation_target() -> None:
    config = _active_config(status=VectorizationStatus.VALIDATING).model_copy(
        update={
            "target_vector_backend": (
                "milvus" if vector_backend_config.backend == "pgvector" else "pgvector"
            ),
            "target_vector_store_fingerprint": "other-store",
            "target_model_fingerprint": "other-model",
        }
    )
    config_service = AsyncMock()
    config_service.get.return_value = config
    redis = AsyncMock()
    app = SimpleNamespace(state=SimpleNamespace(redis_pool=redis))

    with patch(
        "glean_api.vector_lifecycle.TypedConfigService",
        return_value=config_service,
    ):
        result = await reconcile_vector_backend(app, MagicMock())

    assert result is config
    config_service.update_embedding_generation.assert_not_awaited()
    redis.enqueue_job.assert_not_awaited()
