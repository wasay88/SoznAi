from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


__all__ = ["RateLimiter"]
