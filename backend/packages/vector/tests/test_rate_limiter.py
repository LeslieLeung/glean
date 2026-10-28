"""Tests for shared embedding rate limiting."""

from unittest.mock import AsyncMock, patch

import pytest

from glean_core import RedisKeys
from glean_vector.clients.rate_limiter import RateLimitDeadlineError, RateLimiter


@pytest.mark.asyncio
async def test_local_limiter_allows_rpm_requests_without_waiting() -> None:
    limiter = RateLimiter(2)
    with patch("glean_vector.clients.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as sleep:
        await limiter.acquire()
        await limiter.acquire()
        sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_limiter_respects_deadline_instead_of_waiting() -> None:
    limiter = RateLimiter(1)
    await limiter.acquire()
    with pytest.raises(RateLimitDeadlineError):
        await limiter.acquire(deadline=0)


@pytest.mark.asyncio
async def test_redis_limiter_uses_shared_key() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [1, 0]
    limiter = RateLimiter(10, redis=redis)

    await limiter.acquire()

    redis.eval.assert_awaited_once()
    args = redis.eval.await_args
    assert args.args[2] == RedisKeys.EMBEDDING_RATE_LIMIT_KEY
    assert args.args[1] == 1


@pytest.mark.asyncio
async def test_redis_limiter_waits_when_window_is_full() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = [[0, 25], [1, 0]]
    limiter = RateLimiter(10, redis=redis)

    with patch("glean_vector.clients.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as sleep:
        await limiter.acquire()
        sleep.assert_awaited_once()
        assert sleep.await_args.args[0] == pytest.approx(0.025)
    assert redis.eval.await_count == 2
