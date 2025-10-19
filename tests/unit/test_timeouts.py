from __future__ import annotations

import pytest

from backend.app.utils.timeouts import retry_async


@pytest.mark.anyio
async def test_retry_async_success() -> None:
    calls = {"count": 0}

    async def _fn() -> str:
        calls["count"] += 1
        return "ok"

    result = await retry_async(_fn, attempts=3, delay=0.01)

    assert result == "ok"
    assert calls["count"] == 1


@pytest.mark.anyio
async def test_retry_async_exhausts_attempts() -> None:
    async def _fn() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await retry_async(_fn, attempts=2, delay=0)
