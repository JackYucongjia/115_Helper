"""
Token-bucket rate limiter for 115 API calls.

Ensures all outbound API requests respect a global rate limit,
preventing cookie invalidation from 115's anti-abuse system.
"""
from __future__ import annotations

import asyncio
import time
import logging

logger = logging.getLogger("115_helper.rate_limiter")


class RateLimiter:
    """Async token-bucket rate limiter."""

    def __init__(self, rate: float = 2.0, burst: int = 3):
        """
        :param rate:  Max sustained requests per second.
        :param burst: Max burst tokens (allows short bursts).
        """
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a token is available, then consume it."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._rate
                logger.debug("Rate limited — waiting %.2fs", wait_time)
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
                self._last_refill = time.monotonic()
            else:
                self._tokens -= 1.0

    def set_rate(self, rate: float):
        """Dynamically adjust rate limit."""
        self._rate = max(0.1, rate)

    @property
    def rate(self) -> float:
        return self._rate


# Global singleton — shared by all modules
rate_limiter = RateLimiter()
