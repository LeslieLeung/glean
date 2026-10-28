"""Helpers for sizing embedding jobs against rate limits and worker timeout."""

import time
from typing import Any
from uuid import uuid4

from glean_worker.config import (
    EMBEDDING_JOB_DEADLINE_MARGIN_SECONDS,
    MAX_EMBEDDING_JOB_ENTRIES,
    WORKER_JOB_TIMEOUT_SECONDS,
)


def embedding_job_deadline() -> float:
    """Monotonic deadline that stays inside the arq job timeout."""
    usable = max(1, WORKER_JOB_TIMEOUT_SECONDS - EMBEDDING_JOB_DEADLINE_MARGIN_SECONDS)
    return time.monotonic() + usable


def embedding_job_entry_limit(rpm: int, batch_size: int) -> int:
    """Max entries one job can finish under the configured RPM before timeout.

    Provider calls are counted, not entries: a batch of ``batch_size`` texts
    consumes one RPM slot. ``rpm <= 0`` means unlimited requests.
    """
    chunk = max(1, batch_size)
    if rpm <= 0:
        return MAX_EMBEDDING_JOB_ENTRIES
    usable = max(1, WORKER_JOB_TIMEOUT_SECONDS - EMBEDDING_JOB_DEADLINE_MARGIN_SECONDS)
    max_requests = max(1, (usable * rpm) // 60)
    return max(1, min(MAX_EMBEDDING_JOB_ENTRIES, max_requests * chunk))


async def enqueue_embedding_batch_job(
    redis: Any,
    *,
    rpm: int,
    batch_size: int,
    rebuild_id: str | None = None,
    expected_backend: str | None = None,
    expected_store_fingerprint: str | None = None,
    expected_model_fingerprint: str | None = None,
    job_id_prefix: str,
) -> int:
    """Enqueue a single batch embedding job sized to finish within the timeout.

    Rebuild and maintenance used to enqueue one 200-entry job per slice, which
    20 concurrent workers would all claim at once. One continuation-sized job
    plus incremental claiming keeps processing rows within the rate limit.
    """
    limit = embedding_job_entry_limit(rpm, batch_size)
    await redis.enqueue_job(
        "batch_generate_embeddings",
        limit,
        rebuild_id,
        expected_backend,
        expected_store_fingerprint,
        expected_model_fingerprint,
        _job_id=f"{job_id_prefix}_{uuid4().hex}",
    )
    return 1
