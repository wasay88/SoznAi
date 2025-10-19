from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class WeeklyEmotionStat(BaseModel):
    code: str
    count: int
    avg_intensity: float | None = None


class WeeklyDayCount(BaseModel):
    day: int = Field(ge=0, le=6)
    count: int = Field(ge=0)


class WeeklyWordEntry(BaseModel):
    word: str
    count: int


class WeeklyInsightItem(BaseModel):
    week_start: date
    week_end: date
    mood_avg: float | None = None
    mood_volatility: float | None = None
    top_emotions: list[WeeklyEmotionStat]
    wordcloud: list[WeeklyWordEntry]
    days_with_entries: int
    longest_streak: int
    entries_count: int
    entries_by_day: list[WeeklyDayCount]
    summary: str | None = None
    summary_model: str | None = None
    summary_source: str | None = None
    computed_at: datetime


class WeeklyInsightsResponse(BaseModel):
    user_id: int
    range_weeks: int
    items: list[WeeklyInsightItem]


class WeeklyRecomputeRequest(BaseModel):
    user_id: int | None = Field(default=None, alias="user")
    week_start: date | None = None
    weeks: int = Field(default=1, ge=1, le=12)
    force: bool = False
    locale: str | None = None


class WeeklyRecomputeResponse(BaseModel):
    users_processed: int
    weeks_requested: int
    recomputed: int
    debounced: int
    empty: int


__all__ = [
    "WeeklyEmotionStat",
    "WeeklyWordEntry",
    "WeeklyDayCount",
    "WeeklyInsightItem",
    "WeeklyInsightsResponse",
    "WeeklyRecomputeRequest",
    "WeeklyRecomputeResponse",
]
