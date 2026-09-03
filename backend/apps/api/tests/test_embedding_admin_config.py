"""Embedding admin lifecycle compare-and-set regressions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from glean_api.routers.admin import update_embedding_config
from glean_core.schemas.config import (
    EmbeddingConfig,
    EmbeddingConfigUpdateRequest,
    VectorizationStatus,
)


@pytest.mark.asyncio
async def test_config_update_rejects_concurrent_generation_change() -> None:
    current = EmbeddingConfig(
        enabled=False,
        status=VectorizationStatus.DISABLED,
        version="version-1",
    )
    config_service = AsyncMock()
    config_service.get.return_value = current
    config_service.update_embedding_generation.return_value = None
    redis = AsyncMock()

    with (
        patch(
            "glean_core.services.TypedConfigService",
            return_value=config_service,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await update_embedding_config(
            request=EmbeddingConfigUpdateRequest(
                model="replacement-model",
                dimension=current.dimension,
            ),
            current_admin=MagicMock(),
            session=AsyncMock(),
            redis_pool=redis,
        )

    assert exc_info.value.status_code == 409
    redis.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_config_update_cannot_toggle_master_switch() -> None:
    current = EmbeddingConfig(
        enabled=False,
        status=VectorizationStatus.DISABLED,
    )
    config_service = AsyncMock()
    config_service.get.return_value = current

    with (
        patch(
            "glean_core.services.TypedConfigService",
            return_value=config_service,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await update_embedding_config(
            request=EmbeddingConfigUpdateRequest(enabled=True),
            current_admin=MagicMock(),
            session=AsyncMock(),
            redis_pool=AsyncMock(),
        )

    assert exc_info.value.status_code == 400
    config_service.update_embedding_generation.assert_not_awaited()
