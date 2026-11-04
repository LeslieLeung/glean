"""All feed refresh entry points use one job identity and report actual job state."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from arq.jobs import JobStatus

from glean_api.feed_refresh import enqueue_feed_refresh, get_feed_refresh_status


@pytest.mark.asyncio
async def test_duplicate_refresh_reports_existing_job():
    redis = AsyncMock()
    redis.enqueue_job.return_value = None
    with patch("glean_api.feed_refresh.Job") as job:
        job.return_value.status = AsyncMock(return_value=JobStatus.in_progress)
        result = await enqueue_feed_refresh(redis, "f1")
    redis.enqueue_job.assert_awaited_once_with(
        "fetch_feed_task", "f1", _job_id="fetch_feed:f1", _expires=600
    )
    assert result.status == "in_progress"
    assert result.job_id == "fetch_feed:f1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "success,payload,expected",
    [
        (True, {"status": "success", "new_entries": 3}, "success"),
        (True, {"status": "not_modified", "new_entries": 0}, "success"),
        (True, {"status": "error", "message": "HTTP 404"}, "error"),
        (False, RuntimeError("worker unavailable"), "error"),
    ],
)
async def test_refresh_status_uses_worker_result(success, payload, expected):
    with patch("glean_api.feed_refresh.Job") as job:
        job.return_value.status = AsyncMock(return_value=JobStatus.complete)
        job.return_value.result_info = AsyncMock(
            return_value=SimpleNamespace(
                success=success, result=payload, finish_time=datetime.now(UTC)
            )
        )
        result = await get_feed_refresh_status(AsyncMock(), "f1")
    assert result.status == expected
    assert result.finished_at is not None
    if isinstance(payload, dict):
        assert result.new_entries == payload.get("new_entries")


@pytest.mark.asyncio
async def test_expired_queue_payload_is_reported_as_unknown_not_refreshing_forever():
    with patch("glean_api.feed_refresh.Job") as job:
        job.return_value.status = AsyncMock(return_value=JobStatus.queued)
        job.return_value.info = AsyncMock(return_value=None)
        result = await get_feed_refresh_status(AsyncMock(), "f1")
    assert result.status == "unknown"
