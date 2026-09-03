"""Tests for rebuild generation fencing and phase transitions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glean_core import RedisKeys
from glean_core.schemas.config import (
    EmbeddingConfig,
    EmbeddingRebuildPhase,
    VectorizationStatus,
)
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)
from glean_worker.tasks.embedding_maintenance import (
    _enqueue_idle_recovery,
    _enqueue_validation_recovery,
    _enqueue_vector_cleanup_recovery,
)
from glean_worker.tasks.embedding_rebuild import (
    rebuild_embeddings,
    start_preference_rebuild_phase,
)
from glean_worker.tasks.embedding_worker import batch_generate_embeddings


@pytest.mark.asyncio
async def test_preference_phase_uses_current_history_and_generation_id():
    session = AsyncMock()
    redis = MagicMock()
    redis.sadd = AsyncMock()
    redis.expire = AsyncMock()
    redis.enqueue_job = AsyncMock()
    config_service = AsyncMock()
    config_service.get.return_value = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.REBUILDING,
        rebuild_id="generation-1",
        rebuild_phase=EmbeddingRebuildPhase.EMBEDDINGS,
    )

    with patch(
        "glean_worker.tasks.embedding_rebuild.get_preference_history_user_ids",
        new=AsyncMock(return_value=["user-like", "user-bookmark"]),
    ):
        queued = await start_preference_rebuild_phase(
            session,
            redis,
            config_service,
            "generation-1",
        )

    assert queued == 2
    config_service.update_embedding_generation.assert_awaited_once_with(
        expected_version=None,
        expected_rebuild_id="generation-1",
        expected_statuses={VectorizationStatus.REBUILDING.value},
        rebuild_phase=EmbeddingRebuildPhase.PREFERENCES,
    )
    redis.sadd.assert_awaited_once_with(
        RedisKeys.rebuild_preferences("generation-1"),
        "user-like",
        "user-bookmark",
    )
    assert redis.enqueue_job.await_count == 2
    first = redis.enqueue_job.await_args_list[0]
    assert first.args[:3] == (
        "rebuild_user_preference",
        "user-like",
        "generation-1",
    )


@pytest.mark.asyncio
async def test_stale_rebuild_batch_exits_before_touching_vector_storage():
    vector_client = MagicMock()
    vector_client.ensure_collections = AsyncMock()
    session = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.REBUILDING,
        rebuild_id="generation-new",
    )

    with (
        patch(
            "glean_worker.tasks.embedding_worker.ensure_vector_client",
            return_value=(vector_client, None),
        ),
        patch(
            "glean_worker.tasks.embedding_worker.get_session_context",
            return_value=context,
        ),
        patch(
            "glean_worker.tasks.embedding_worker._check_vectorization_enabled",
            new=AsyncMock(return_value=(True, config)),
        ),
    ):
        result = await batch_generate_embeddings(
            {"vector_client": vector_client},
            rebuild_id="generation-old",
        )

    assert result["skipped"] == "Stale rebuild job"
    vector_client.ensure_collections.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_maintenance_recovers_pending_and_failed_with_throttle():
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=[True, True])
    redis.enqueue_job = AsyncMock()

    pending, failed = await _enqueue_idle_recovery(
        redis,
        {"pending": 3, "failed": 2, "processing": 0},
    )

    assert (pending, failed) == (1, 1)
    assert redis.enqueue_job.await_args_list[0].args == (
        "batch_generate_embeddings",
        200,
        None,
    )
    assert redis.enqueue_job.await_args_list[1].args == (
        "retry_failed_embeddings",
        200,
    )


@pytest.mark.asyncio
async def test_idle_maintenance_does_not_compete_with_processing_jobs():
    redis = MagicMock()
    redis.set = AsyncMock()
    redis.enqueue_job = AsyncMock()

    queued = await _enqueue_idle_recovery(
        redis,
        {"pending": 3, "failed": 2, "processing": 1},
    )

    assert queued == (0, 0)
    redis.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_maintenance_recovers_lost_validation_job() -> None:
    config = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.VALIDATING,
        version="version-1",
        target_vector_backend=vector_backend_config.backend,
        target_vector_store_fingerprint=vector_store_fingerprint(),
        target_model_fingerprint=embedding_model_fingerprint(
            "openai",
            "text-embedding-3-small",
            1536,
            None,
        ),
        target_force_rebuild=True,
    )
    redis = AsyncMock()
    redis.set.return_value = True

    queued = await _enqueue_validation_recovery(redis, config)

    assert queued == 1
    redis.enqueue_job.assert_awaited_once()
    assert redis.enqueue_job.await_args.kwargs["force_rebuild"] is True
    assert redis.enqueue_job.await_args.kwargs["expected_version"] == "version-1"


@pytest.mark.asyncio
async def test_maintenance_recovers_durable_vector_cleanup_outbox() -> None:
    result = MagicMock()
    result.all.return_value = [
        ("entry-1", "feed-1"),
        ("entry-2", "feed-1"),
        ("entry-3", "feed-2"),
    ]
    session = AsyncMock()
    session.execute.return_value = result
    redis = AsyncMock()
    redis.set.return_value = True

    queued = await _enqueue_vector_cleanup_recovery(session, redis)

    assert queued == 2
    assert redis.enqueue_job.await_args_list[0].args[:3] == (
        "cleanup_orphan_embeddings",
        "feed-1",
        ["entry-1", "entry-2"],
    )


@pytest.mark.asyncio
async def test_rebuild_failure_records_terminal_error_state():
    """A failure after rebuild starts must not leave maintenance to declare success."""
    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.release = AsyncMock()
    redis = MagicMock()
    redis.lock.return_value = lock
    session = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    config_service = AsyncMock()
    config_service.get.return_value = EmbeddingConfig(
        enabled=True,
        status=VectorizationStatus.VALIDATING,
    )

    with (
        patch(
            "glean_worker.tasks.embedding_rebuild.get_session_context",
            return_value=context,
        ),
        patch(
            "glean_worker.tasks.embedding_rebuild.TypedConfigService",
            return_value=config_service,
        ),
        patch(
            "glean_worker.tasks.embedding_rebuild.ensure_vector_client",
            return_value=(MagicMock(), None),
        ),
        patch(
            "glean_worker.tasks.embedding_rebuild._rebuild_embeddings_locked",
            new=AsyncMock(side_effect=RuntimeError("recreate failed")),
        ),
        patch(
            "glean_worker.tasks.embedding_rebuild._mark_rebuild_error_for_version",
            new=AsyncMock(),
        ) as mark_error,
    ):
        result = await rebuild_embeddings({"redis": redis})

    assert result == {"success": False, "error": "recreate failed"}
    mark_error.assert_awaited_once()
    assert str(mark_error.await_args.args[0]) == "recreate failed"
    assert mark_error.await_args.kwargs == {"expected_version": None}
    lock.release.assert_awaited_once()
