from unittest.mock import AsyncMock

import pytest

from backend.app.ai.costs import DailyLimiter


@pytest.mark.anyio
async def test_daily_limiter_transitions() -> None:
    storage = AsyncMock()
    storage.usage_total_since.return_value = 0.0
    limiter = DailyLimiter(storage, soft_limit=0.05, hard_limit=0.1)
    await limiter.refresh()
    assert limiter.mode == "normal"

    limiter.register(0.05)
    assert limiter.mode == "soft"

    limiter.register(0.05)
    assert limiter.mode == "hard"

    info = limiter.info()
    assert info["mode"] == "hard"
    assert info["today_spend"] >= 0.1
