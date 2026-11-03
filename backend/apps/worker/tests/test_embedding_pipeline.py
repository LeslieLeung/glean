"""Exercise worker pipelines with real PostgreSQL sessions and pgvector storage."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.models import Bookmark, Entry, Feed, SystemConfig, User, UserEntry
from glean_vector.clients.pgvector_client import PgVectorClient
from glean_vector.config import (
    embedding_model_fingerprint,
    pgvector_config,
    vector_backend_config,
    vector_store_fingerprint,
)
from glean_worker.tasks.embedding_worker import (
    batch_generate_embeddings,
    generate_entry_embedding,
    validate_and_rebuild_embeddings,
)


@pytest.fixture
async def pipeline(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[dict[str, Any]]:
    import glean_database.session as database_session

    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(database_session, "_async_session_maker", sessions)
    monkeypatch.setattr(vector_backend_config, "backend", "pgvector")
    monkeypatch.setattr(
        pgvector_config, "database_url", test_engine.url.render_as_string(hide_password=False)
    )
    redis = MagicMock()
    redis.enqueue_job = AsyncMock()
    sets: dict[str, set[str]] = {}

    async def sadd(key: str, *members: str) -> int:
        target = sets.setdefault(key, set())
        before = len(target)
        target.update(members)
        return len(target) - before

    async def srem(key: str, member: str) -> int:
        target = sets.setdefault(key, set())
        found = member in target
        target.discard(member)
        return int(found)

    redis.sadd = AsyncMock(side_effect=sadd)
    redis.srem = AsyncMock(side_effect=srem)
    redis.smembers = AsyncMock(side_effect=lambda key: sets.get(key, set()).copy())
    redis.scard = AsyncMock(side_effect=lambda key: len(sets.get(key, set())))
    redis.exists = AsyncMock(side_effect=lambda key: bool(sets.get(key)))
    redis.delete = AsyncMock(side_effect=lambda key: sets.pop(key, None))
    redis.expire = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.lock.return_value.acquire = AsyncMock(return_value=True)
    redis.lock.return_value.release = AsyncMock()
    provider = AsyncMock()

    async def generate(texts: list[str]) -> tuple[list[list[float]], dict[str, Any]]:
        return [[1.0, 0.0, 0.0] for _ in texts], {}

    provider.generate_embeddings_batch.side_effect = generate
    monkeypatch.setattr(
        "glean_vector.clients.embedding_client.EmbeddingProviderFactory.create",
        lambda **kwargs: provider,
    )
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.IDLE,
        version=str(uuid4()),
        provider="openai",
        model="pipeline-test",
        dimension=3,
        batch_size=3,
        rate_limit={"default": 0, "providers": {}},
        vector_backend="pgvector",
        vector_store_fingerprint=vector_store_fingerprint(),
        model_fingerprint=embedding_model_fingerprint("openai", "pipeline-test", 3, None),
    )
    feed_id = str(uuid4())
    user_ids: list[str] = []
    client = PgVectorClient()
    async with sessions() as session:
        original_config = await session.get(SystemConfig, EmbeddingConfig.NAMESPACE)
        original_value = dict(original_config.value) if original_config else None
        session.add(Feed(id=feed_id, url=f"https://example.com/{feed_id}"))
        await TypedConfigService(session).set(EmbeddingConfig, config)
    await client.recreate_collections(3, config.provider, config.model)
    try:
        yield {
            "sessions": sessions,
            "config": config,
            "feed_id": feed_id,
            "client": client,
            "redis": redis,
            "provider": provider,
            "user_ids": user_ids,
        }
    finally:
        await client.disconnect()
        async with sessions() as session:
            await session.execute(delete(Feed).where(Feed.id == feed_id))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.execute(delete(SystemConfig).where(SystemConfig.key == "embedding"))
            if original_value is not None:
                session.add(SystemConfig(key="embedding", value=original_value))
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_entry", [False, True])
async def test_batch_pipeline_preserves_loaded_entries_across_fences_and_rollbacks(
    pipeline: dict[str, Any], empty_entry: bool
) -> None:
    """A failed/committed item must not expire the rest of an ORM-backed batch."""
    entry_ids = [str(uuid4()) for _ in range(3)]
    async with pipeline["sessions"]() as session:
        session.add_all(
            Entry(
                id=entry_id,
                feed_id=pipeline["feed_id"],
                url=f"https://example.com/{entry_id}",
                title="" if empty_entry and index == 0 else f"Article {index}",
            )
            for index, entry_id in enumerate(entry_ids)
        )
        await session.commit()

    result = await batch_generate_embeddings(
        {"vector_client": pipeline["client"], "redis": pipeline["redis"]},
        limit=3,
    )

    assert result == {"processed": 2 if empty_entry else 3, "failed": int(empty_entry)}
    async with pipeline["sessions"]() as session:
        rows = await session.execute(
            select(Entry.id, Entry.embedding_status).where(Entry.id.in_(entry_ids))
        )
        assert dict(rows.all()) == {
            entry_id: "failed" if empty_entry and index == 0 else "done"
            for index, entry_id in enumerate(entry_ids)
        }
    vectors = await pipeline["client"].batch_get_entry_embeddings(entry_ids)
    assert set(vectors) == set(entry_ids[1:] if empty_entry else entry_ids)


@pytest.mark.asyncio
async def test_validation_rebuilds_when_compatible_store_has_lost_vectors(
    pipeline: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matching signatures must not hide a lost vector after startup reconciliation."""
    config = pipeline["config"]
    async with pipeline["sessions"]() as session:
        session.add(
            Entry(
                feed_id=pipeline["feed_id"],
                url="https://example.com/lost-vector",
                title="Previously embedded article",
                embedding_status="done",
            )
        )
        await TypedConfigService(session).update(
            EmbeddingConfig,
            status=VectorizationStatus.VALIDATING,
            target_vector_backend="pgvector",
            target_vector_store_fingerprint=config.vector_store_fingerprint,
            target_model_fingerprint=config.model_fingerprint,
        )
    monkeypatch.setattr(
        "glean_vector.services.EmbeddingValidationService.validate_provider",
        AsyncMock(return_value=MagicMock(success=True)),
    )

    result = await validate_and_rebuild_embeddings(
        {"vector_client": pipeline["client"], "redis": pipeline["redis"]},
        expected_version=config.version,
    )

    assert result["success"] is True
    assert not result.get("skipped_rebuild")
    pipeline["redis"].enqueue_job.assert_awaited_once()
    assert pipeline["redis"].enqueue_job.call_args.args == ("rebuild_embeddings",)


@pytest.mark.asyncio
async def test_single_entry_claim_releases_row_lock_before_provider_call(
    pipeline: dict[str, Any],
) -> None:
    """A network wait must not hold a row lock needed by a fenced rebuild."""
    entry_id = str(uuid4())
    async with pipeline["sessions"]() as session:
        session.add(
            Entry(
                id=entry_id,
                feed_id=pipeline["feed_id"],
                url="https://example.com/single",
                title="Single",
            )
        )
        await session.commit()

    async def generate(_text: str) -> tuple[list[float], dict[str, Any]]:
        async with pipeline["sessions"]() as session:
            status = await session.scalar(
                select(Entry.embedding_status).where(Entry.id == entry_id)
            )
            assert status == "processing"
            await session.execute(text("SET LOCAL lock_timeout = '200ms'"))
            await session.execute(
                text("SELECT id FROM entries WHERE id = :id FOR UPDATE"), {"id": entry_id}
            )
        return [1.0, 0.0, 0.0], {}

    pipeline["provider"].generate_embedding.side_effect = generate
    result = await generate_entry_embedding(
        {"vector_client": pipeline["client"], "redis": pipeline["redis"]}, entry_id
    )
    assert result == {"success": True, "entry_id": entry_id}


@pytest.mark.asyncio
async def test_full_rebuild_reaches_idle_after_rebuilding_reactions_and_bookmarks(
    pipeline: dict[str, Any],
) -> None:
    from glean_worker.tasks.embedding_maintenance import scheduled_embedding_maintenance
    from glean_worker.tasks.embedding_rebuild import rebuild_embeddings
    from glean_worker.tasks.preference_worker import rebuild_user_preference

    entry_ids = [str(uuid4()) for _ in range(4)]
    user_ids = [str(uuid4()) for _ in range(2)]
    pipeline["user_ids"].extend(user_ids)
    async with pipeline["sessions"]() as session:
        session.add_all(User(id=user_id) for user_id in user_ids)
        session.add_all(
            Entry(
                id=entry_id,
                feed_id=pipeline["feed_id"],
                url=f"https://example.com/{entry_id}",
                title="History",
            )
            for entry_id in entry_ids
        )
        await session.flush()
        session.add(UserEntry(user_id=user_ids[0], entry_id=entry_ids[0], is_liked=True))
        session.add(UserEntry(user_id=user_ids[0], entry_id=entry_ids[1], is_liked=False))
        session.add(
            Bookmark(
                user_id=user_ids[1],
                entry_id=entry_ids[2],
                url=f"https://example.com/{entry_ids[2]}",
                title="Saved",
            )
        )
        await TypedConfigService(session).update(
            EmbeddingConfig, status=VectorizationStatus.VALIDATING
        )

    ctx = {"vector_client": pipeline["client"], "redis": pipeline["redis"]}
    result = await rebuild_embeddings(ctx, expected_version=pipeline["config"].version)
    assert result["success"] is True
    assert result["queued_entries"] == 4
    rebuild_id = result["rebuild_id"]
    assert await batch_generate_embeddings(ctx, limit=4, rebuild_id=rebuild_id) == {
        "processed": 4,
        "failed": 0,
    }
    maintenance = await scheduled_embedding_maintenance(ctx)
    assert maintenance["queued_preference_rebuilds"] == 2
    for user_id in user_ids:
        assert (await rebuild_user_preference(ctx, user_id, rebuild_id))["success"] is True

    async with pipeline["sessions"]() as session:
        config = await TypedConfigService(session).get(EmbeddingConfig)
        assert config.status == VectorizationStatus.IDLE
        assert config.rebuild_id is None
        users = (await session.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        assert all(
            user.preference_revision == user.preference_synced_revision > 0 for user in users
        )
    reactions = await pipeline["client"].get_user_preferences(user_ids[0])
    assert set(reactions) == {"positive", "negative"}
    assert reactions["positive"]["sample_count"] == pytest.approx(1.0)
    bookmarks = await pipeline["client"].get_user_preferences(user_ids[1])
    assert bookmarks["positive"]["sample_count"] == pytest.approx(0.7)
