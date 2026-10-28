"""Tests for embedding job sizing against RPM and worker timeout."""

from unittest.mock import AsyncMock

import pytest

from glean_worker.tasks.embedding_limits import (
    embedding_job_entry_limit,
    enqueue_embedding_batch_job,
)


def test_entry_limit_fits_default_rpm_without_batching() -> None:
    """10 RPM and one-text requests must finish inside the 300s job timeout."""
    assert embedding_job_entry_limit(10, 1) == 40


def test_entry_limit_uses_provider_batch_size() -> None:
    """A 20-text provider request consumes one RPM slot."""
    assert embedding_job_entry_limit(10, 20) == 200


def test_unlimited_rpm_still_caps_one_job() -> None:
    assert embedding_job_entry_limit(0, 20) == 200


@pytest.mark.asyncio
async def test_enqueue_embedding_batch_job_queues_a_single_sized_job() -> None:
    redis = AsyncMock()

    queued = await enqueue_embedding_batch_job(
        redis,
        rpm=10,
        batch_size=1,
        rebuild_id="rebuild-1",
        expected_backend="pgvector",
        expected_store_fingerprint="store",
        expected_model_fingerprint="model",
        job_id_prefix="rebuild",
    )

    assert queued == 1
    redis.enqueue_job.assert_awaited_once()
    args = redis.enqueue_job.await_args
    assert args.args == (
        "batch_generate_embeddings",
        40,
        "rebuild-1",
        "pgvector",
        "store",
        "model",
    )
    assert args.kwargs["_job_id"].startswith("rebuild_")
