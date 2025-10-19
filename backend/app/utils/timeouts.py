from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(func: Callable[[], Awaitable[T]], attempts: int, delay: float) -> T:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                await asyncio.sleep(delay)
    if last_exc is None:
        raise RuntimeError("retry_async failed without exception")
    raise last_exc
