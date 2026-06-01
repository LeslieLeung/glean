"""Tests for score-service dependency behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glean_api.dependencies import get_score_service
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_vector.services.score_service import ScoreService


@pytest.mark.asyncio
async def test_get_score_service_reuses_app_scoped_vector_client() -> None:
    """Should reuse the app-scoped vector client after ensuring storage."""
    session = AsyncMock()
    vector_client = AsyncMock()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(vector_client=vector_client))
    )
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.IDLE,
        provider="openai",
        model="text-embedding-3-small",
        dimension=1536,
    )

    with (
        patch("glean_core.services.TypedConfigService") as config_service_cls,
        patch("glean_vector.services.score_service.ScoreService") as score_service_cls,
    ):
        config_service = AsyncMock()
        config_service.get.return_value = config
        config_service_cls.return_value = config_service

        sentinel_service = MagicMock(spec=ScoreService)
        score_service_cls.return_value = sentinel_service

        service = await get_score_service(request=request, session=session)

    assert service is sentinel_service
    vector_client.ensure_collections.assert_awaited_once_with(
        config.dimension,
        config.provider,
        config.model,
    )
    score_service_cls.assert_called_once_with(
        db_session=session,
        vector_client=vector_client,
    )


@pytest.mark.asyncio
async def test_get_score_service_falls_back_when_vector_client_missing() -> None:
    """Should return SimpleScoreService when startup did not initialize a client."""
    session = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(vector_client=None)))
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.IDLE,
        provider="openai",
        model="text-embedding-3-small",
        dimension=1536,
    )

    with patch("glean_core.services.TypedConfigService") as config_service_cls:
        config_service = AsyncMock()
        config_service.get.return_value = config
        config_service_cls.return_value = config_service

        service = await get_score_service(request=request, session=session)

    from glean_core.services import SimpleScoreService

    assert isinstance(service, SimpleScoreService)
