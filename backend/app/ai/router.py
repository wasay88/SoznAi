from __future__ import annotations

import logging
from dataclasses import dataclass

from ..core.config import Settings
from ..services.storage import StorageService
from .cache import PromptCache
from .costs import DailyLimiter, HardLimitExceeded, UsageRecord, UsageTracker
from .local_llm import generate_local_response
from .openai_client import OpenAIClient
from .templates import choose_template

logger = logging.getLogger(__name__)


@dataclass
class AIResponse:
    text: str
    source: str
    model: str
    tokens_in: int
    tokens_out: int
    usd_cost: float
    cached: bool = False


class AIRouter:
    """Routes AI prompts across OpenAI models, templates and local fallbacks."""

    def __init__(
        self,
        *,
        settings: Settings,
        storage: StorageService,
        cache: PromptCache,
        usage_tracker: UsageTracker,
        limiter: DailyLimiter,
        openai_client: OpenAIClient,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._cache = cache
        self._usage_tracker = usage_tracker
        self._limiter = limiter
        self._openai = openai_client
        self._mode = settings.ai_router_mode
        self._primary_model = settings.openai_model_primary
        self._deep_model = settings.openai_model_deep
        self._max_tokens_quick = settings.ai_max_tokens_quick
        self._max_tokens_deep = settings.ai_max_tokens_deep

    async def initialize(self) -> None:
        config = await self._storage.ensure_ai_config(
            default_mode=self._mode,
            soft_limit=self._settings.openai_soft_limit_usd,
            hard_limit=self._settings.openai_daily_limit_usd,
        )
        self._mode = config["mode"]
        self._limiter.set_limits(config["soft_limit"], config["hard_limit"])
        await self._limiter.refresh()

    # ------------------------------------------------------------------
    async def ask(
        self,
        *,
        user_id: int | None,
        kind: str,
        text: str,
        locale: str = "ru",
        use_cache: bool = True,
    ) -> AIResponse:
        locale_norm = locale if locale in {"ru", "en"} else "ru"

        if use_cache:
            cached = await self._cache.get(kind, text, locale_norm)
            if cached:
                await self._usage_tracker.record_cache_hit(
                    kind=kind,
                    model=cached.model,
                    user_id=user_id,
                )
                return AIResponse(
                    text=cached.text,
                    source="cache",
                    model=cached.model,
                    tokens_in=cached.tokens_in,
                    tokens_out=cached.tokens_out,
                    usd_cost=0.0,
                    cached=True,
                )

        limiter_mode = self._limiter.mode
        if limiter_mode == "hard":
            logger.warning(
                "daily ai budget exhausted",
                extra={"user_id": user_id, "kind": kind, "mode": self._mode},
            )
            raise HardLimitExceeded("Дневной лимит ИИ исчерпан. Попробуйте снова завтра.")

        route = self._select_route(kind, limiter_mode)
        logger.debug("AI route selected", extra={"kind": kind, "route": route, "mode": self._mode})

        if route == "template":
            reply = choose_template(kind, locale_norm)
            await self._usage_tracker.record_zero_cost(
                kind=kind,
                model="template",
                source="template",
                user_id=user_id,
            )
            return AIResponse(reply, "template", "template", 0, 0, 0.0)

        if route == "local":
            reply = generate_local_response(kind, text, locale_norm)
            await self._usage_tracker.record_zero_cost(
                kind=kind,
                model="local",
                source="local",
                user_id=user_id,
            )
            return AIResponse(reply, "local", "local", 0, 0, 0.0)

        model = self._primary_model if route == "mini" else self._deep_model
        max_tokens = self._max_tokens_quick if route == "mini" else self._max_tokens_deep
        try:
            response_text, tokens_in, tokens_out, cost = await self._openai.complete(
                model=model,
                prompt=text,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("AI request failed, falling back to local: %s", exc)
            fallback = generate_local_response(kind, text, locale_norm)
            await self._usage_tracker.record_zero_cost(
                kind=kind,
                model="local",
                source="local",
                user_id=user_id,
            )
            return AIResponse(fallback, "local", "local", 0, 0, 0.0)

        record = UsageRecord(
            model=model,
            kind=kind,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            usd_cost=cost,
            source=route,
            user_id=user_id,
        )
        await self._usage_tracker.record(record)

        response = AIResponse(
            text=response_text.strip() or generate_local_response(kind, text, locale_norm),
            source=route,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            usd_cost=cost,
        )

        await self._cache.set(
            kind=kind,
            prompt=text,
            locale=locale_norm,
            response_text=response.text,
            model=model,
            source=route,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            usd_cost=cost,
        )
        return response

    def _select_route(self, kind: str, limiter_mode: str) -> str:
        base = self._base_route_for_kind(kind)
        forced = self._mode
        if forced == "local_only":
            return "local"
        if forced == "mini_only":
            base = "mini"
        elif forced == "turbo_only":
            base = "turbo"

        if limiter_mode == "hard":
            return "local"
        if limiter_mode == "soft" and base == "turbo":
            base = "mini"

        if base == "turbo" and not self._settings.openai_api_key:
            base = "mini"
        if base in {"mini", "turbo"} and not self._settings.openai_api_key:
            return "local"
        return base

    @staticmethod
    def _base_route_for_kind(kind: str) -> str:
        if kind in {"quick_tip", "breathing_hint"}:
            return "template"
        if kind == "mood_reply":
            return "mini"
        if kind in {"deep_insight", "weekly_review"}:
            return "turbo"
        return "mini"

    # -- admin helpers -------------------------------------------------
    async def set_mode(self, mode: str, *, actor: str = "admin") -> str:
        normalized = mode if mode in {"auto", "mini_only", "local_only", "turbo_only"} else "auto"
        self._mode = normalized
        await self._storage.update_ai_mode(normalized, actor=actor)
        return normalized

    async def set_limits(
        self, soft_limit: float, hard_limit: float, *, actor: str = "admin"
    ) -> dict[str, float]:
        stored = await self._storage.update_ai_limits(soft_limit, hard_limit, actor=actor)
        self._limiter.set_limits(stored["soft_limit"], stored["hard_limit"])
        return stored

    async def refresh_limits(self) -> None:
        await self._usage_tracker.refresh_limits()

    def limiter_info(self) -> dict[str, float | str]:
        return self._usage_tracker.limiter_info()

    async def usage_stats(self, days: int = 7) -> list[dict[str, object]]:
        return await self._storage.usage_totals(days)

    def current_mode(self) -> str:
        return self._mode

    @property
    def mode(self) -> str:
        return self._mode
