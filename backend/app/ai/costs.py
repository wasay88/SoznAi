from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ..metrics import AI_COST, AI_REQUESTS, AI_TOKENS


@runtime_checkable
class StorageService(Protocol):  # pragma: no cover - structural typing helper
    async def usage_total_since(self, start: datetime) -> float: ...

    async def record_usage(
        self,
        *,
        user_id: int | None,
        model: str,
        kind: str,
        source: str,
        tokens_in: int,
        tokens_out: int,
        usd_cost: float,
    ) -> None: ...


@dataclass
class UsageRecord:
    model: str
    kind: str
    tokens_in: int
    tokens_out: int
    usd_cost: float
    source: str
    user_id: int | None = None


class DailyLimiter:
    """Tracks daily spend and exposes downgrade/disable states."""

    def __init__(
        self,
        storage: StorageService,
        soft_limit: float,
        hard_limit: float,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._storage = storage
        self._soft_limit = max(0.0, soft_limit)
        self._hard_limit = max(self._soft_limit, hard_limit)
        self._today_spend = 0.0
        self._mode = "normal"  # normal | soft | hard
        self._last_refreshed: datetime | None = None
        self._clock: Callable[[], datetime] = clock or datetime.utcnow

    async def refresh(self) -> None:
        now = self._clock()
        self._ensure_current_day(now)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self._today_spend = await self._storage.usage_total_since(start_of_day)
        self._update_mode()
        self._last_refreshed = now

    def _update_mode(self) -> None:
        if self._today_spend >= self._hard_limit:
            self._mode = "hard"
        elif self._today_spend >= self._soft_limit:
            self._mode = "soft"
        else:
            self._mode = "normal"

    def register(self, usd_cost: float) -> None:
        now = self._clock()
        self._ensure_current_day(now)
        self._today_spend += usd_cost
        self._update_mode()
        self._last_refreshed = now

    def set_limits(self, soft_limit: float, hard_limit: float) -> None:
        self._ensure_current_day()
        self._soft_limit = max(0.0, soft_limit)
        self._hard_limit = max(self._soft_limit, hard_limit)
        self._update_mode()

    @property
    def mode(self) -> str:
        self._ensure_current_day()
        return self._mode

    @property
    def soft_limit(self) -> float:
        return self._soft_limit

    @property
    def hard_limit(self) -> float:
        return self._hard_limit

    @property
    def today_spend(self) -> float:
        self._ensure_current_day()
        return self._today_spend

    def info(self) -> dict[str, float | str]:
        self._ensure_current_day()
        return {
            "mode": self._mode,
            "soft_limit": self._soft_limit,
            "hard_limit": self._hard_limit,
            "today_spend": round(self._today_spend, 4),
        }

    def _ensure_current_day(self, now: datetime | None = None) -> datetime:
        """Reset tracked spend when the wall-clock rolls over to a new day."""

        current = now or self._clock()

        if self._last_refreshed is None:
            self._last_refreshed = current
            return current

        if self._last_refreshed.date() != current.date():
            self._today_spend = 0.0
            self._mode = "normal"

        self._last_refreshed = current
        return current


class UsageTracker:
    """Persists usage records and updates Prometheus counters."""

    def __init__(self, storage: StorageService, limiter: DailyLimiter) -> None:
        self._storage = storage
        self._limiter = limiter

    async def record(self, record: UsageRecord) -> None:
        await self._storage.record_usage(
            user_id=record.user_id,
            model=record.model,
            kind=record.kind,
            source=record.source,
            tokens_in=record.tokens_in,
            tokens_out=record.tokens_out,
            usd_cost=record.usd_cost,
        )
        AI_REQUESTS.labels(record.source, record.kind, record.model).inc()
        AI_TOKENS.labels("in").inc(record.tokens_in)
        AI_TOKENS.labels("out").inc(record.tokens_out)
        AI_COST.inc(record.usd_cost)
        self._limiter.register(record.usd_cost)

    async def refresh_limits(self) -> None:
        await self._limiter.refresh()

    def limiter_info(self) -> dict[str, float | str]:
        return self._limiter.info()

    def set_limits(self, soft_limit: float, hard_limit: float) -> None:
        self._limiter.set_limits(soft_limit, hard_limit)

    @property
    def limiter(self) -> DailyLimiter:
        return self._limiter

    async def record_cache_hit(
        self, *, kind: str, model: str, user_id: int | None = None
    ) -> None:
        await self._storage.record_usage(
            user_id=user_id,
            model=model,
            kind=kind,
            source="cache",
            tokens_in=0,
            tokens_out=0,
            usd_cost=0.0,
        )
        AI_REQUESTS.labels("cache", kind, model).inc()

    async def record_zero_cost(
        self,
        *,
        kind: str,
        model: str,
        source: str,
        user_id: int | None = None,
    ) -> None:
        await self._storage.record_usage(
            user_id=user_id,
            model=model,
            kind=kind,
            source=source,
            tokens_in=0,
            tokens_out=0,
            usd_cost=0.0,
        )
        AI_REQUESTS.labels(source, kind, model).inc()
