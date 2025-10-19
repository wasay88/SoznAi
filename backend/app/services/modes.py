from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum


class ModeState(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    DEGRADED = "degraded"


@dataclass
class ModeStatus:
    state: ModeState
    reason: str | None = None

    @property
    def online(self) -> bool:
        return self.state == ModeState.ONLINE


@dataclass
class ModeManager:
    """Holds application mode and exposes helpers for transitions."""

    _status: ModeStatus = field(
        default_factory=lambda: ModeStatus(ModeState.OFFLINE, "bot token missing"),
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def set_online(self, reason: str | None = None) -> ModeStatus:
        async with self._lock:
            self._status = ModeStatus(ModeState.ONLINE, reason)
            return self._status

    async def set_degraded(self, reason: str) -> ModeStatus:
        async with self._lock:
            self._status = ModeStatus(ModeState.DEGRADED, reason)
            return self._status

    async def set_offline(self, reason: str) -> ModeStatus:
        async with self._lock:
            self._status = ModeStatus(ModeState.OFFLINE, reason)
            return self._status

    async def get_status(self) -> ModeStatus:
        async with self._lock:
            return self._status

    def snapshot(self) -> ModeStatus:
        return self._status
