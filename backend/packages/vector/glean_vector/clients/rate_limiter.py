"""
Simple in-process rate limiter for embedding calls (rpm).
"""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Sliding window rate limiter (requests per minute)."""

    def __init__(self, rpm: int) -> None:
        self.rpm = max(1, rpm)
        self._lock = asyncio.Lock()
        self._timestamps: list[float] = []

    async def acquire(self) -> None:
        """Block until within rate limit."""
        async with self._lock:
            now = time.time()
            window_start = now - 60
            # Drop old timestamps
            self._timestamps = [ts for ts in self._timestamps if ts > window_start]

            if len(self._timestamps) >= self.rpm:
                sleep_time = self._timestamps[0] + 60 - now
                await asyncio.sleep(max(0, sleep_time))
                # After sleep, clean again
                now = time.time()
                window_start = now - 60
                self._timestamps = [ts for ts in self._timestamps if ts > window_start]

            self._timestamps.append(time.time())

