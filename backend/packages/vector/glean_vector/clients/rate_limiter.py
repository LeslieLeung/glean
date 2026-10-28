"""
Rate limiter for embedding provider calls (requests per minute).

When a Redis client is provided, the sliding window is global so concurrent
worker jobs share one RPM budget. Without Redis the limiter is in-process.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from glean_core import RedisKeys, get_logger

logger = get_logger(__name__)

_WINDOW_MS = 60_000
_KEY_TTL_SECONDS = 120

# Atomic sliding-window acquire. Returns {allowed, wait_ms}.
_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now, member)
  redis.call('EXPIRE', key, ttl)
  return {1, 0}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local wait_ms = 0
if #oldest >= 2 then
  wait_ms = tonumber(oldest[2]) + window - now
  if wait_ms < 0 then
    wait_ms = 0
  end
end
return {0, wait_ms}
"""


class RateLimitDeadlineError(Exception):
    """No rate-limit slot was available before the job deadline."""


class RateLimiter:
    """Sliding window rate limiter (requests per minute)."""

    def __init__(self, rpm: int, redis: Any | None = None, key: str | None = None) -> None:
        self.rpm = max(1, rpm)
        self._redis = redis
        self._key = key or RedisKeys.EMBEDDING_RATE_LIMIT_KEY
        self._lock = asyncio.Lock()
        self._timestamps: list[float] = []

    async def acquire(self, *, deadline: float | None = None) -> None:
        """Block until a slot is available, or raise if the deadline is reached."""
        if self._redis is not None:
            await self._acquire_redis(deadline=deadline)
            return
        await self._acquire_local(deadline=deadline)

    async def _acquire_local(self, *, deadline: float | None) -> None:
        while True:
            _raise_if_deadline_passed(deadline)
            async with self._lock:
                now = time.time()
                window_start = now - 60
                self._timestamps = [ts for ts in self._timestamps if ts > window_start]
                if len(self._timestamps) < self.rpm:
                    self._timestamps.append(now)
                    return
                sleep_time = self._timestamps[0] + 60 - now
            await _sleep_until_slot(sleep_time, deadline=deadline)

    async def _acquire_redis(self, *, deadline: float | None) -> None:
        redis = self._redis
        if redis is None:
            raise RuntimeError("Redis rate limiter requires a Redis client")
        while True:
            _raise_if_deadline_passed(deadline)
            now_ms = int(time.time() * 1000)
            member = f"{now_ms}-{uuid.uuid4().hex}"
            try:
                result = await redis.eval(
                    _ACQUIRE_SCRIPT,
                    1,
                    self._key,
                    now_ms,
                    _WINDOW_MS,
                    self.rpm,
                    member,
                    _KEY_TTL_SECONDS,
                )
            except RateLimitDeadlineError:
                raise
            except Exception:
                logger.warning(
                    "Embedding rate limiter Redis acquire failed; retrying",
                    extra={"key": self._key},
                    exc_info=True,
                )
                await _sleep_until_slot(0.1, deadline=deadline)
                continue

            allowed, wait_ms = _parse_acquire_result(result)
            if allowed:
                return
            await _sleep_until_slot(wait_ms / 1000.0, deadline=deadline)


def _parse_acquire_result(result: Any) -> tuple[bool, int]:
    """Normalize Redis EVAL return values to (allowed, wait_ms)."""
    if not isinstance(result, (list, tuple)):
        return False, 0
    values: list[Any] = list(result)  # type: ignore[arg-type]
    if len(values) < 2:
        return False, 0
    return bool(int(values[0])), max(0, int(values[1]))


def _raise_if_deadline_passed(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise RateLimitDeadlineError()


async def _sleep_until_slot(sleep_time: float, *, deadline: float | None) -> None:
    """Sleep for the limiter wait, without crossing the job deadline."""
    wait = max(0.0, sleep_time)
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RateLimitDeadlineError()
        if wait >= remaining:
            raise RateLimitDeadlineError()
    if wait > 0:
        await asyncio.sleep(wait)
