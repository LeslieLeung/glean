"""Embedding config compare-and-set and first-write concurrency tests."""

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from glean_core.schemas.config import (
    EmbeddingConfig,
    VectorizationStatus,
)
from glean_core.services import TypedConfigService
from glean_database.models import SystemConfig


@pytest.mark.asyncio
async def test_stale_embedding_generation_update_is_rejected(
    db_session: AsyncSession,
) -> None:
    service = TypedConfigService(db_session)
    await service.update(
        EmbeddingConfig,
        version="version-1",
        provider="openai",
    )
    await service.update(EmbeddingConfig, version="version-2")

    stale = await service.update_embedding_generation(
        expected_version="version-1",
        expected_rebuild_id=None,
        expected_statuses={VectorizationStatus.DISABLED.value},
        provider="stale-provider",
    )

    assert stale is None
    current = await service.get(EmbeddingConfig)
    assert current.version == "version-2"
    assert current.provider == "openai"


@pytest.mark.asyncio
async def test_concurrent_first_writes_create_one_config_row(
    test_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as cleanup_session:
        await TypedConfigService(cleanup_session).delete(EmbeddingConfig)
        await cleanup_session.commit()

    async def write(model: str) -> None:
        async with session_factory() as session:
            await TypedConfigService(session).update(
                EmbeddingConfig,
                model=model,
            )

    await asyncio.gather(write("model-a"), write("model-b"))

    async with session_factory() as session:
        row_count = await session.scalar(
            select(func.count())
            .select_from(SystemConfig)
            .where(SystemConfig.key == EmbeddingConfig.NAMESPACE)
        )
        config = await TypedConfigService(session).get(EmbeddingConfig)
        assert row_count == 1
        assert config.model in {"model-a", "model-b"}
        await TypedConfigService(session).delete(EmbeddingConfig)
