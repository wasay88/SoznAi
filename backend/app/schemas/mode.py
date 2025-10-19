from __future__ import annotations

from pydantic import BaseModel

from ..services.modes import ModeState


class ModeResponse(BaseModel):
    mode: ModeState
    online: bool
    reason: str | None = None


class ModeUpdate(BaseModel):
    target_mode: ModeState
    reason: str | None = None
