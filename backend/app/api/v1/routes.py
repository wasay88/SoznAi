from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from ...ai import run_daily_insights
from ...ai.costs import HardLimitExceeded
from ...ai.router import AIRouter
from ...core.security import (
    enforce_webhook_secret,
    optional_admin_token,
    require_admin_token,
    resolve_authenticated_user,
)
from ...insights import WeeklyInsightsEngine
from ...metrics import USER_API_COUNTER
from ...schemas.ai import (
    AIAdminOverview,
    AIAdminStatsResponse,
    AIAskRequest,
    AIAskResponse,
    AIBatchToggle,
    AICacheOverview,
    AIChartPoint,
    AIKindBreakdown,
    AILimitStatus,
    AILimitsUpdate,
    AIModeUpdate,
    AIUsageHistoryItem,
    AIUsageHistoryResponse,
    InsightEntryModel,
    InsightListResponse,
)
from ...schemas.analytics import AnalyticsQuery, AnalyticsSummary
from ...schemas.auth import AuthSessionInfo, MagicLinkRequest
from ...schemas.emotion import (
    EmotionCreate,
    EmotionCreateResponse,
    EmotionEntryModel,
    EmotionListResponse,
)
from ...schemas.insights import (
    WeeklyDayCount,
    WeeklyEmotionStat,
    WeeklyInsightItem,
    WeeklyInsightsResponse,
    WeeklyRecomputeRequest,
    WeeklyRecomputeResponse,
    WeeklyWordEntry,
)
from ...schemas.journal import (
    JournalCreate,
    JournalCreateResponse,
    JournalEntryModel,
    JournalListResponse,
)
from ...schemas.mode import ModeResponse, ModeUpdate
from ...schemas.webhook import TelegramWebhookUpdate, WebhookResponse
from ...services.modes import ModeManager, ModeState
from ...services.ratelimit import RateLimiter
from ...services.storage import StorageService
from ...services.telegram import TelegramService

router = APIRouter(prefix="/api/v1", tags=["core"])


def get_mode_manager(request: Request) -> ModeManager:
    return request.app.state.mode_manager


def get_telegram_service(request: Request) -> TelegramService:
    return request.app.state.telegram_service


def get_storage_service(request: Request) -> StorageService:
    return request.app.state.storage_service


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_ai_router(request: Request) -> AIRouter:
    return request.app.state.ai_router


def get_weekly_insights_engine(request: Request) -> WeeklyInsightsEngine:
    return request.app.state.weekly_insights


def _hash_user_identifier(user_id: int | None) -> str | None:
    if user_id is None:
        return None
    digest = sha256(str(user_id).encode("utf-8")).hexdigest()
    return digest[:12]


@router.get("/mode", response_model=ModeResponse)
async def read_mode(mode_manager: ModeManager = Depends(get_mode_manager)) -> ModeResponse:
    status = await mode_manager.get_status()
    return ModeResponse(mode=status.state, online=status.online, reason=status.reason)


@router.post("/mode", response_model=ModeResponse)
async def update_mode(
    payload: ModeUpdate,
    mode_manager: ModeManager = Depends(get_mode_manager),
) -> ModeResponse:
    if payload.target_mode == ModeState.ONLINE:
        status_obj = await mode_manager.set_online(payload.reason)
    elif payload.target_mode == ModeState.DEGRADED:
        status_obj = await mode_manager.set_degraded(payload.reason or "manual switch")
    else:
        status_obj = await mode_manager.set_offline(payload.reason or "manual switch")
    return ModeResponse(
        mode=status_obj.state,
        online=status_obj.online,
        reason=status_obj.reason,
    )


@router.post("/webhook", response_model=WebhookResponse)
async def handle_webhook(
    update: TelegramWebhookUpdate,
    mode_manager: ModeManager = Depends(get_mode_manager),
    telegram_service: TelegramService = Depends(get_telegram_service),
    _: None = Depends(enforce_webhook_secret),
) -> WebhookResponse:
    if not telegram_service.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram unavailable",
        )
    return await telegram_service.process_update(update, mode_manager)


@router.post(
    "/journal",
    response_model=JournalCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_journal_entry(
    payload: JournalCreate,
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> JournalCreateResponse:
    if not limiter.allow(f"journal:{user_id}", limit=20, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    entry = await storage.add_journal_entry(
        user_id=user_id,
        text=payload.text,
        source=payload.source or "api",
    )
    USER_API_COUNTER.labels(endpoint="journal_post").inc()
    return JournalCreateResponse(id=entry.id)


@router.get("/journal", response_model=JournalListResponse)
async def list_journal_entries(
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
    limit: int = Query(default=20, ge=1, le=100),
) -> JournalListResponse:
    entries = await storage.list_journal_entries(user_id=user_id, limit=limit)
    items = [JournalEntryModel.model_validate(e, from_attributes=True) for e in entries]
    USER_API_COUNTER.labels(endpoint="journal_get").inc()
    return JournalListResponse(items=items)


@router.post(
    "/emotions",
    response_model=EmotionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_emotion_entry(
    payload: EmotionCreate,
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> EmotionCreateResponse:
    if not limiter.allow(f"emotion:{user_id}", limit=40, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    entry = await storage.add_emotion_entry(
        user_id=user_id,
        emotion_code=payload.emotion_code,
        intensity=payload.intensity,
        note=payload.note,
        source=payload.source or "api",
    )
    USER_API_COUNTER.labels(endpoint="emotions_post").inc()
    return EmotionCreateResponse(id=entry.id)


@router.get("/emotions", response_model=EmotionListResponse)
async def list_emotion_entries(
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
    limit: int = Query(default=20, ge=1, le=100),
) -> EmotionListResponse:
    entries = await storage.list_emotion_entries(user_id=user_id, limit=limit)
    items = [EmotionEntryModel.model_validate(e, from_attributes=True) for e in entries]
    USER_API_COUNTER.labels(endpoint="emotions_get").inc()
    return EmotionListResponse(items=items)


@router.post("/ai/ask", response_model=AIAskResponse)
async def ai_ask(
    payload: AIAskRequest,
    router: AIRouter = Depends(get_ai_router),
    user_id: int = Depends(resolve_authenticated_user),
) -> AIAskResponse:
    try:
        response = await router.ask(
            user_id=user_id,
            kind=payload.kind,
            text=payload.text,
            locale=payload.locale or "ru",
        )
    except HardLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    USER_API_COUNTER.labels(endpoint="ai_ask").inc()
    return AIAskResponse(
        text=response.text,
        source=response.source,
        model=response.model,
        cost=round(response.usd_cost, 6),
        cached=response.cached,
    )


@router.get("/ai/limits", response_model=AILimitStatus)
async def ai_limits(router: AIRouter = Depends(get_ai_router)) -> AILimitStatus:
    await router.refresh_limits()
    info = router.limiter_info()
    return AILimitStatus(
        soft=float(info["soft_limit"]),
        hard=float(info["hard_limit"]),
        today_spend=float(info["today_spend"]),
        mode=str(info["mode"]),
    )


@router.get("/insights", response_model=InsightListResponse)
async def list_insights(
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
    limit: int = Query(default=7, ge=1, le=30),
) -> InsightListResponse:
    rows = await storage.list_insights(user_id=user_id, limit=limit)
    items = [InsightEntryModel(day=row.day, text=row.text) for row in rows]
    USER_API_COUNTER.labels(endpoint="insights_get").inc()
    return InsightListResponse(items=items)


@router.get("/insights/weekly", response_model=WeeklyInsightsResponse)
async def get_weekly_insights(
    storage: StorageService = Depends(get_storage_service),
    engine: WeeklyInsightsEngine = Depends(get_weekly_insights_engine),
    user_id: int = Depends(resolve_authenticated_user),
    range_weeks: int = Query(default=4, ge=1, le=12, alias="range"),
    target_user: int | None = Query(default=None, alias="user"),
    locale: str = Query(default="ru"),
    is_admin: bool = Depends(optional_admin_token),
) -> WeeklyInsightsResponse:
    target_id = user_id
    if target_user and target_user != user_id:
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        target_id = target_user

    locale_norm = locale if locale in {"ru", "en"} else "ru"
    await engine.ensure_range(
        target_id,
        weeks=range_weeks,
        locale=locale_norm,
    )
    rows = await storage.list_weekly_insights(target_id, limit=range_weeks)
    items: list[WeeklyInsightItem] = []
    for row in rows:
        top_raw = json.loads(row.top_emotions or "[]")
        words_raw = json.loads(row.journal_wordcloud or "[]")
        day_raw = json.loads(row.entries_by_day or "[]")
        top = [WeeklyEmotionStat.model_validate(item) for item in top_raw]
        wordcloud = [WeeklyWordEntry.model_validate(item) for item in words_raw]
        day_counts = [WeeklyDayCount.model_validate(item) for item in day_raw]
        items.append(
            WeeklyInsightItem(
                week_start=row.week_start,
                week_end=row.week_end,
                mood_avg=row.mood_avg,
                mood_volatility=row.mood_volatility,
                top_emotions=top,
                wordcloud=wordcloud,
                days_with_entries=row.days_with_entries,
                longest_streak=row.longest_streak,
                entries_count=row.entries_count,
                entries_by_day=day_counts,
                summary=row.summary,
                summary_model=row.summary_model,
                summary_source=row.summary_source,
                computed_at=row.computed_at,
            )
        )
    USER_API_COUNTER.labels(endpoint="insights_weekly_get").inc()
    return WeeklyInsightsResponse(user_id=target_id, range_weeks=range_weeks, items=items)


@router.post("/auth/magiclink", response_model=AuthSessionInfo)
async def create_magic_link(
    payload: MagicLinkRequest,
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
) -> AuthSessionInfo:
    session_token = await storage.issue_magic_link(user_id=user_id, email=payload.email)
    USER_API_COUNTER.labels(endpoint="auth_magiclink").inc()
    return AuthSessionInfo(token=session_token.token, expires_at=session_token.expires_at)


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    query: AnalyticsQuery = Depends(),
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
) -> AnalyticsSummary:
    summary = await storage.analytics_summary(user_id=user_id, days=query.days)
    USER_API_COUNTER.labels(endpoint="analytics_summary").inc()
    return AnalyticsSummary.model_validate(summary)


@router.get("/me/export")
async def export_me(
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
) -> StreamingResponse:
    content = await storage.export_user_data(user_id=user_id, days=30)
    USER_API_COUNTER.labels(endpoint="me_export").inc()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=soznai-export.csv"},
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    storage: StorageService = Depends(get_storage_service),
    user_id: int = Depends(resolve_authenticated_user),
) -> Response:
    await storage.delete_user(user_id)
    USER_API_COUNTER.labels(endpoint="me_delete").inc()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/ai/stats", response_model=AIAdminStatsResponse)
async def admin_ai_stats(
    router: AIRouter = Depends(get_ai_router),
    storage: StorageService = Depends(get_storage_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
    days: int = Query(default=7, ge=1, le=30),
    _: None = Depends(require_admin_token),
) -> AIAdminStatsResponse:
    window = 7 if days < 15 else 30
    if window not in {7, 30}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="range unsupported")
    if not limiter.allow("admin:stats", limit=30, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")

    usage_buckets = await router.usage_stats(days=window)
    overview = await storage.usage_overview(days=window)
    info = router.limiter_info()
    limits = await storage.get_ai_limits()
    batch_enabled = await storage.is_batch_enabled()

    cost_per_day: dict[str, float] = {}
    tokens_per_model: dict[str, int] = {}
    for bucket in usage_buckets:
        day_total = cost_per_day.get(bucket["day"], 0.0)
        cost_per_day[bucket["day"]] = day_total + float(bucket["usd_cost"])
        model_total = tokens_per_model.get(bucket["model"], 0)
        tokens_per_model[bucket["model"]] = (
            model_total + bucket["tokens_in"] + bucket["tokens_out"]
        )

    overview_model = AIAdminOverview(
        today_spend=float(info.get("today_spend", 0.0)),
        mode=router.current_mode(),
        limiter_mode=str(info.get("mode", "normal")),
        soft_limit=float(limits["soft_limit"]),
        hard_limit=float(limits["hard_limit"]),
        requests=overview["requests"],
        tokens_in=overview["tokens_in"],
        tokens_out=overview["tokens_out"],
        cache_hits=overview["cache_hits"],
        cache_hit_rate=round(overview["cache_rate"], 4),
        batch_enabled=batch_enabled,
    )

    cost_points = [
        AIChartPoint(label=day, value=round(value, 4))
        for day, value in sorted(cost_per_day.items())
    ]
    model_points = [
        AIChartPoint(label=model, value=total, model=model)
        for model, total in sorted(tokens_per_model.items())
    ]
    kind_breakdown = [
        AIKindBreakdown(label=kind, value=count)
        for kind, count in sorted(overview["requests_by_kind"].items())
    ]

    return AIAdminStatsResponse(
        overview=overview_model,
        cost_per_day=cost_points,
        tokens_per_model=model_points,
        requests_by_kind=kind_breakdown,
    )


@router.post("/admin/ai/mode")
async def admin_set_mode(
    payload: AIModeUpdate,
    router: AIRouter = Depends(get_ai_router),
    limiter: RateLimiter = Depends(get_rate_limiter),
    _: None = Depends(require_admin_token),
) -> dict[str, str]:
    if not limiter.allow("admin:mode", limit=10, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    mode = await router.set_mode(payload.mode, actor="admin")
    return {"mode": mode}


@router.post("/admin/ai/limits", response_model=AILimitStatus)
async def admin_set_limits(
    payload: AILimitsUpdate,
    router: AIRouter = Depends(get_ai_router),
    limiter: RateLimiter = Depends(get_rate_limiter),
    _: None = Depends(require_admin_token),
) -> AILimitStatus:
    if not limiter.allow("admin:limits", limit=10, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    stored = await router.set_limits(payload.soft, payload.hard, actor="admin")
    await router.refresh_limits()
    info = router.limiter_info()
    return AILimitStatus(
        soft=float(stored["soft_limit"]),
        hard=float(stored["hard_limit"]),
        today_spend=float(info["today_spend"]),
        mode=str(info["mode"]),
    )


@router.post("/admin/ai/batch")
async def admin_toggle_batch(
    payload: AIBatchToggle,
    storage: StorageService = Depends(get_storage_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
    _: None = Depends(require_admin_token),
) -> dict[str, bool]:
    if not limiter.allow("admin:batch", limit=10, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    enabled = await storage.set_batch_enabled(payload.enabled)
    return {"enabled": enabled}


@router.get("/admin/cache", response_model=AICacheOverview)
async def admin_cache_snapshot(
    storage: StorageService = Depends(get_storage_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
    days: int = Query(default=7, ge=1, le=30),
    _: None = Depends(require_admin_token),
) -> AICacheOverview:
    if not limiter.allow("admin:cache", limit=30, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    if days not in {7, 30}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="range unsupported")
    snapshot = await storage.cache_overview(days=days)
    return AICacheOverview.model_validate(snapshot)


@router.get("/admin/ai/history", response_model=AIUsageHistoryResponse)
async def admin_usage_history(
    storage: StorageService = Depends(get_storage_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
    limit: int = Query(default=50, ge=1, le=100),
    _: None = Depends(require_admin_token),
) -> AIUsageHistoryResponse:
    if not limiter.allow("admin:history", limit=30, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    rows = await storage.usage_history(limit)
    items = [
        AIUsageHistoryItem(
            ts=row.ts,
            model=row.model,
            kind=row.kind,
            source=row.source,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            usd_cost=float(row.usd_cost),
            user_hash=_hash_user_identifier(row.user_id),
        )
        for row in rows
    ]
    return AIUsageHistoryResponse(items=items)


@router.post("/admin/run/daily")
async def admin_run_daily(
    router: AIRouter = Depends(get_ai_router),
    storage: StorageService = Depends(get_storage_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
    _: None = Depends(require_admin_token),
) -> dict[str, int]:
    if not limiter.allow("admin:daily", limit=5, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    created = await run_daily_insights(storage, router)
    return {"created": created}


@router.post("/insights/recompute", response_model=WeeklyRecomputeResponse)
async def recompute_weekly_insights(
    payload: WeeklyRecomputeRequest,
    storage: StorageService = Depends(get_storage_service),
    engine: WeeklyInsightsEngine = Depends(get_weekly_insights_engine),
    _: None = Depends(require_admin_token),
) -> WeeklyRecomputeResponse:
    locale = payload.locale if payload.locale in {"ru", "en"} else "ru"
    if payload.user_id is not None:
        user_ids = [payload.user_id]
    else:
        since = datetime.utcnow() - timedelta(days=30)
        user_ids = list(await storage.list_recent_users(since))
    if not user_ids:
        return WeeklyRecomputeResponse(
            users_processed=0,
            weeks_requested=payload.weeks,
            recomputed=0,
            debounced=0,
            empty=0,
        )
    updated, debounced, empty = await engine.recompute_for_users(
        user_ids,
        weeks=payload.weeks,
        week_start=payload.week_start,
        force=payload.force,
        locale=locale,
    )
    return WeeklyRecomputeResponse(
        users_processed=len(user_ids),
        weeks_requested=payload.weeks,
        recomputed=updated,
        debounced=debounced,
        empty=empty,
    )
