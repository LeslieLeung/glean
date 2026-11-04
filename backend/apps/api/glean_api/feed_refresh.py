"""Shared feed job status; authorization is checked by the subscription router."""

from typing import Any, cast

from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus

from glean_core.feed_jobs import FEED_QUEUE_EXPIRY_SECONDS, feed_job_id
from glean_core.schemas.feed import FeedRefreshResponse


async def get_feed_refresh_status(redis: ArqRedis, feed_id: str) -> FeedRefreshResponse:
    job_id = feed_job_id(feed_id)
    job = Job(job_id, redis, _queue_name=redis.default_queue_name)
    status = await job.status()
    response = FeedRefreshResponse(status="idle", job_id=job_id, feed_id=feed_id)
    if status in (JobStatus.queued, JobStatus.deferred):
        # An expired payload can leave a queue entry behind while workers are offline.
        response.status = "queued" if await job.info() is not None else "unknown"
    elif status == JobStatus.in_progress:
        response.status = "in_progress"
    elif status == JobStatus.complete:
        result = await job.result_info()
        if result is not None:
            raw_result: Any = cast(Any, result).result
            payload = cast(dict[str, Any], raw_result) if isinstance(raw_result, dict) else {}
            response.status = (
                "error" if not result.success or payload.get("status") == "error" else "success"
            )
            response.finished_at = result.finish_time
            response.new_entries = payload.get("new_entries")
            response.message = payload.get("message") if result.success else "Feed refresh failed"
    return response


async def enqueue_feed_refresh(redis: ArqRedis, feed_id: str) -> FeedRefreshResponse:
    job = await redis.enqueue_job(
        "fetch_feed_task",
        feed_id,
        _job_id=feed_job_id(feed_id),
        _expires=FEED_QUEUE_EXPIRY_SECONDS,
    )
    if job is not None:
        return FeedRefreshResponse(status="queued", job_id=job.job_id, feed_id=feed_id)
    return await get_feed_refresh_status(redis, feed_id)
