from __future__ import annotations

import time

from backend.app.services.ratelimit import RateLimiter


def test_rate_limiter_allows_within_limit() -> None:
    limiter = RateLimiter()
    for _ in range(3):
        assert limiter.allow("key", limit=3, window_seconds=1)


def test_rate_limiter_blocks_after_limit(monkeypatch) -> None:
    limiter = RateLimiter()
    monotonic_values = iter([0.0, 0.1, 0.2, 0.3])
    monkeypatch.setattr(time, "monotonic", lambda: next(monotonic_values))
    assert limiter.allow("key", limit=2, window_seconds=1)
    assert limiter.allow("key", limit=2, window_seconds=1)
    assert limiter.allow("key", limit=2, window_seconds=1) is False
