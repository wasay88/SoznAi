from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EmotionAggregate(BaseModel):
    code: str = Field(..., min_length=1)
    count: int = Field(..., ge=0)


class AnalyticsSummary(BaseModel):
    streak_days: int
    entries_count: int
    mood_avg: float | None
    top_emotions: list[EmotionAggregate]
    last_entry_ts: datetime | None


class AnalyticsQuery(BaseModel):
    range: Literal["7d", "30d"] = "7d"

    @property
    def days(self) -> int:
        return 7 if self.range == "7d" else 30
