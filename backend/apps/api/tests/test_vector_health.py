"""Tests for vector-aware API readiness."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from glean_api.main import health_check
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)


@asynccontextmanager
async def _session_context():
    yield AsyncMock()


@pytest.mark.asyncio
async def test_health_is_unavailable_when_enabled_vector_backend_cannot_recover() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.IDLE,
        provider="openai",
        model="text-embedding-3-small",
        dimension=1536,
        vector_backend=vector_backend_config.backend,
        vector_store_fingerprint=vector_store_fingerprint(),
        model_fingerprint=embedding_model_fingerprint(
            "openai",
            "text-embedding-3-small",
            1536,
            None,
        ),
    )

    with (
        patch("glean_database.session.get_session_context", return_value=_session_context()),
        patch("glean_core.services.TypedConfigService") as config_service_cls,
        patch(
            "glean_api.main.ensure_app_vector_client",
            AsyncMock(return_value=(None, "connection refused")),
        ),
    ):
        config_service_cls.return_value.get = AsyncMock(return_value=config)

        with pytest.raises(HTTPException) as exc_info:
            await health_check(request)

    assert exc_info.value.status_code == 503
    assert "connection refused" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_health_ignores_vector_backend_when_vectorization_disabled() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    config = EmbeddingConfig(
        enabled=False,
        status=VectorizationStatus.DISABLED,
    )

    with (
        patch("glean_database.session.get_session_context", return_value=_session_context()),
        patch("glean_core.services.TypedConfigService") as config_service_cls,
        patch("glean_api.main.ensure_app_vector_client") as ensure_client,
    ):
        config_service_cls.return_value.get = AsyncMock(return_value=config)
        result = await health_check(request)

    assert result["status"] == "healthy"
    ensure_client.assert_not_called()
