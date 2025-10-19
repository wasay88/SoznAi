from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.ai.batch_jobs import run_daily_insights
from backend.app.ai.cache import PromptCache
from backend.app.ai.costs import DailyLimiter, UsageTracker
from backend.app.ai.router import AIRouter
from backend.app.services.storage import StorageService


class DummyOpenAI:
    async def complete(self, *, model: str, prompt: str, max_tokens: int):
        return "insight " * 12, 40, 50, 0.01


@pytest.mark.anyio
async def test_run_daily_insights_creates_entry(temp_session_factory) -> None:
    storage = StorageService(temp_session_factory)
    settings = SimpleNamespace(
        ai_router_mode="auto",
        openai_soft_limit_usd=1.0,
        openai_daily_limit_usd=2.0,
        openai_api_key="fake",
        openai_model_primary="gpt-mini",
        openai_model_deep="gpt-turbo",
        ai_cache_ttl_sec=3600,
        ai_max_tokens_quick=120,
        ai_max_tokens_deep=400,
    )
    limiter = DailyLimiter(storage, settings.openai_soft_limit_usd, settings.openai_daily_limit_usd)
    usage_tracker = UsageTracker(storage, limiter)
    cache = PromptCache(storage, settings.ai_cache_ttl_sec)
    router = AIRouter(
        settings=settings,
        storage=storage,
        cache=cache,
        usage_tracker=usage_tracker,
        limiter=limiter,
        openai_client=DummyOpenAI(),
    )
    await router.initialize()

    user = await storage.ensure_user_by_telegram(42)
    await storage.add_emotion_entry(
        user_id=user.id, emotion_code="joy", intensity=4, note="", source="test"
    )
    await storage.add_journal_entry(user_id=user.id, text="Сегодня всё спокойно", source="test")

    created = await run_daily_insights(storage, router, hours=24)
    assert created >= 1

    insights = await storage.list_insights(user_id=user.id, limit=1)
    assert insights and "insight" in insights[0].text
