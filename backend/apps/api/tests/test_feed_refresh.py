"""All feed refresh entry points use one job identity and report actual job state."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from arq.connections import ArqRedis
from arq.constants import default_queue_name, job_key_prefix, result_key_prefix
from arq.jobs import JobStatus, serialize_job, serialize_result

from glean_api.feed_refresh import enqueue_feed_refresh, get_feed_refresh_status
from glean_core import arq_json_serializer


class _FakePipeline:
    def __init__(self, redis: "_FakeArqRedis") -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def exists(self, key: str) -> "_FakePipeline":
        self._commands.append(("exists", (key,)))
        return self

    def zscore(self, key: str, member: str) -> "_FakePipeline":
        self._commands.append(("zscore", (key, member)))
        return self

    async def execute(self) -> list[Any]:
        results = []
        for cmd, args in self._commands:
            results.append(await getattr(self._redis, cmd)(*args))
        self._commands.clear()
        return results


class _FakeArqRedis:
    def __init__(self) -> None:
        self.default_queue_name = default_queue_name
        self._data: dict[str, bytes] = {}
        self._zsets: dict[str, dict[str, int]] = {}

    async def get(self, key: str) -> bytes | None:
        return self._data.get(key)

    async def exists(self, key: str) -> int:
        return 1 if key in self._data else 0

    async def zscore(self, key: str, member: str) -> float | None:
        score = self._zsets.get(key, {}).get(member)
        return float(score) if score is not None else None

    def pipeline(self, transaction: bool = True) -> _FakePipeline:  # noqa: ARG002
        return _FakePipeline(self)


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


@pytest.mark.asyncio
async def test_get_feed_refresh_status_deserializes_json_queued_job():
    redis = _FakeArqRedis()
    job_id = "fetch_feed:f1"
    enqueue_ms = int(datetime.now(UTC).timestamp() * 1000) - 1000
    redis._data[job_key_prefix + job_id] = serialize_job(
        "fetch_feed_task",
        ("f1",),
        {},
        1,
        enqueue_ms,
        serializer=arq_json_serializer,
    )
    redis._zsets[default_queue_name] = {job_id: enqueue_ms}

    result = await get_feed_refresh_status(cast(ArqRedis, redis), "f1")
    assert result.status == "queued"
    assert result.job_id == job_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "success,payload,expected_status,expected_entries,expected_message",
    [
        (True, {"status": "success", "new_entries": 4}, "success", 4, None),
        (False, RuntimeError("boom"), "error", None, "Feed refresh failed"),
    ],
)
async def test_get_feed_refresh_status_deserializes_json_result(
    success: bool,
    payload: Any,
    expected_status: str,
    expected_entries: int | None,
    expected_message: str | None,
):
    redis = _FakeArqRedis()
    job_id = "fetch_feed:f1"
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    serialized = serialize_result(
        "fetch_feed_task",
        ("f1",),
        {},
        1,
        now_ms - 500,
        success,
        payload,
        now_ms - 400,
        now_ms,
        "fetch_feed_task",
        default_queue_name,
        job_id,
        serializer=arq_json_serializer,
    )
    assert serialized is not None
    redis._data[result_key_prefix + job_id] = serialized

    result = await get_feed_refresh_status(cast(ArqRedis, redis), "f1")
    assert result.status == expected_status
    assert result.new_entries == expected_entries
    assert result.message == expected_message
    assert result.finished_at is not None
