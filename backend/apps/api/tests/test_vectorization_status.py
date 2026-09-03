"""Tests for runtime vectorization status reporting."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from glean_api.routers.system import get_vectorization_status
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)


def _active_config() -> EmbeddingConfig:
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.IDLE,
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
async def test_vectorization_status_reports_runtime_backend_failure() -> None:
    config = _active_config()
    config_service = AsyncMock()
    config_service.get.return_value = config
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(vector_client_error="vector connection refused"))
    )

    with patch(
        "glean_api.routers.system.ensure_app_vector_client",
        AsyncMock(return_value=(None, "vector connection refused")),
    ):
        response = await get_vectorization_status(
            request=request,
            config_service=config_service,
            session=AsyncMock(),
        )

    assert response.status == VectorizationStatus.ERROR
    assert response.has_error is True
    assert response.error_message == "vector connection refused"


@pytest.mark.asyncio
async def test_vectorization_status_clears_transient_error_after_recovery() -> None:
    config = _active_config()
    config_service = AsyncMock()
    config_service.get.return_value = config
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(vector_client_error="startup failure"))
    )

    with patch(
        "glean_api.routers.system.ensure_app_vector_client",
        AsyncMock(return_value=(object(), None)),
    ):
        response = await get_vectorization_status(
            request=request,
            config_service=config_service,
            session=AsyncMock(),
        )

    assert response.status == VectorizationStatus.IDLE
    assert response.has_error is False
    assert response.error_message is None
