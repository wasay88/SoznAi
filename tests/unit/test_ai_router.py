from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.ai.cache import PromptCache
from backend.app.ai.costs import DailyLimiter, HardLimitExceeded, UsageTracker
from backend.app.ai.router import AIRouter
from backend.app.services.storage import StorageService


class DummyOpenAI:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, model: str, prompt: str, max_tokens: int):
        self.calls += 1
        text = "insight " * 12
        return text, 50, 60, 0.01


@pytest.mark.anyio
async def test_ai_router_routes_and_caches(temp_session_factory) -> None:
    storage = StorageService(temp_session_factory)
    settings = SimpleNamespace(
        ai_router_mode="auto",
        openai_soft_limit_usd=0.01,
        openai_daily_limit_usd=0.02,
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
    openai = DummyOpenAI()
    router = AIRouter(
        settings=settings,
        storage=storage,
        cache=cache,
        usage_tracker=usage_tracker,
        limiter=limiter,
        openai_client=openai,
    )
    await router.initialize()

    template_response = await router.ask(user_id=1, kind="quick_tip", text="need help", locale="ru")
    assert template_response.source in {"template", "local"}
    assert template_response.text

    model_response = await router.ask(
        user_id=1,
        kind="deep_insight",
        text="provide detail",
        locale="ru",
    )
    assert model_response.source in {"turbo", "mini"}
    assert openai.calls == 1

    cached_response = await router.ask(
        user_id=1,
        kind="deep_insight",
        text="provide detail",
        locale="ru",
    )
    assert cached_response.cached is True
    assert openai.calls == 1

    info = router.limiter_info()
    assert info["today_spend"] >= 0
    stats = await router.usage_stats()
    assert stats


@pytest.mark.anyio
async def test_ai_router_forced_modes_and_limits(temp_session_factory) -> None:
    storage = StorageService(temp_session_factory)
    settings = SimpleNamespace(
        ai_router_mode="auto",
        openai_soft_limit_usd=0.05,
        openai_daily_limit_usd=0.06,
        openai_api_key="fake",
        openai_model_primary="gpt-mini",
        openai_model_deep="gpt-turbo",
        ai_cache_ttl_sec=10,
        ai_max_tokens_quick=120,
        ai_max_tokens_deep=400,
    )
    limiter = DailyLimiter(storage, settings.openai_soft_limit_usd, settings.openai_daily_limit_usd)
    usage_tracker = UsageTracker(storage, limiter)
    cache = PromptCache(storage, settings.ai_cache_ttl_sec)
    openai = DummyOpenAI()
    router = AIRouter(
        settings=settings,
        storage=storage,
        cache=cache,
        usage_tracker=usage_tracker,
        limiter=limiter,
        openai_client=openai,
    )
    await router.initialize()

    forced_local = await router.set_mode("local_only")
    assert forced_local == "local_only"
    local_response = await router.ask(
        user_id=None,
        kind="deep_insight",
        text="local case",
        use_cache=False,
    )
    assert local_response.source == "local"

    await router.set_mode("turbo_only")
    settings.openai_api_key = ""
    turbo_without_key = await router.ask(
        user_id=None,
        kind="weekly_review",
        text="check key",
        use_cache=False,
    )
    assert turbo_without_key.source == "local"

    settings.openai_api_key = "fake"
    await router.set_mode("auto")
    await router.set_limits(0.01, 0.015)

    first = await router.ask(user_id=1, kind="deep_insight", text="first unique", use_cache=False)
    assert first.source == "turbo"
    assert openai.calls == 1

    second = await router.ask(user_id=1, kind="deep_insight", text="second unique", use_cache=False)
    assert second.source == "mini"
    assert openai.calls == 2

    with pytest.raises(HardLimitExceeded):
        await router.ask(user_id=1, kind="deep_insight", text="third unique", use_cache=False)
    assert openai.calls == 2
