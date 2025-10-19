from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class AIAskRequest(BaseModel):
    kind: str = Field(..., examples=["quick_tip", "deep_insight"])
    text: str = Field(..., min_length=1, max_length=2000)
    locale: str | None = Field(default=None)


class AIAskResponse(BaseModel):
    text: str
    source: str
    model: str
    cost: float
    cached: bool = False


class AILimitStatus(BaseModel):
    soft: float
    hard: float
    today_spend: float
    mode: str


class AILimitsUpdate(BaseModel):
    soft: float = Field(..., ge=0)
    hard: float = Field(..., ge=0)


class AIModeUpdate(BaseModel):
    mode: str = Field(..., pattern="^(auto|mini_only|local_only|turbo_only)$")


class AIUsageBucket(BaseModel):
    day: str
    model: str
    tokens_in: int
    tokens_out: int
    usd_cost: float
    requests: int


class AIUsageResponse(BaseModel):
    buckets: list[AIUsageBucket]


class AIAdminOverview(BaseModel):
    today_spend: float
    mode: str
    limiter_mode: str
    soft_limit: float
    hard_limit: float
    requests: int
    tokens_in: int
    tokens_out: int
    cache_hits: int
    cache_hit_rate: float
    batch_enabled: bool


class AIChartPoint(BaseModel):
    label: str
    value: float
    model: str | None = None


class AIKindBreakdown(BaseModel):
    label: str
    value: int


class AIAdminStatsResponse(BaseModel):
    overview: AIAdminOverview
    cost_per_day: list[AIChartPoint]
    tokens_per_model: list[AIChartPoint]
    requests_by_kind: list[AIKindBreakdown]


class AIUsageHistoryItem(BaseModel):
    ts: datetime
    model: str
    kind: str
    source: str
    tokens_in: int
    tokens_out: int
    usd_cost: float
    user_hash: str | None = None


class AIUsageHistoryResponse(BaseModel):
    items: list[AIUsageHistoryItem]


class InsightEntryModel(BaseModel):
    day: date
    text: str


class InsightListResponse(BaseModel):
    items: list[InsightEntryModel]


class AIBatchToggle(BaseModel):
    enabled: bool


class AICacheKeyInfo(BaseModel):
    key: str
    kind: str
    locale: str
    model: str
    expires_at: datetime


class AICacheOverview(BaseModel):
    hits: int
    misses: int
    hit_rate: float
    keys: list[AICacheKeyInfo]
