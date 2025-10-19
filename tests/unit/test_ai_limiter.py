import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.app.ai.costs import DailyLimiter


def _run(coro):
    return asyncio.run(coro)


def test_daily_limiter_transitions() -> None:
    storage = AsyncMock()
    storage.usage_total_since.return_value = 0.0
    limiter = DailyLimiter(storage, soft_limit=0.05, hard_limit=0.1)
    _run(limiter.refresh())
    assert limiter.mode == "normal"

    limiter.register(0.05)
    assert limiter.mode == "soft"

    limiter.register(0.05)
    assert limiter.mode == "hard"

    info = limiter.info()
    assert info["mode"] == "hard"
    assert info["today_spend"] >= 0.1


def test_daily_limiter_resets_on_new_day() -> None:
    class DummyClock:
        def __init__(self, now: datetime) -> None:
            self.now = now

        def __call__(self) -> datetime:
            return self.now

    storage = AsyncMock()
    storage.usage_total_since.return_value = 0.0
    clock = DummyClock(datetime(2024, 5, 1, 12, 0, 0))
    limiter = DailyLimiter(storage, soft_limit=0.05, hard_limit=0.1, clock=clock)
    _run(limiter.refresh())

    limiter.register(0.12)
    assert limiter.mode == "hard"
    assert limiter.today_spend == pytest.approx(0.12)

    clock.now = clock.now + timedelta(days=1)

    assert limiter.mode == "normal"
    assert limiter.today_spend == pytest.approx(0.0)
    limiter.register(0.02)

    assert limiter.mode == "normal"
    assert limiter.today_spend == pytest.approx(0.02)
    info = limiter.info()
    assert info["mode"] == "normal"
    assert info["today_spend"] == pytest.approx(0.02, rel=1e-6)
