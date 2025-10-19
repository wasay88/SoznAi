"""AI companion routing, caching and batch jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "AIResponse",
    "AIRouter",
    "DailyLimiter",
    "PromptCache",
    "UsageTracker",
    "choose_template",
    "run_daily_insights",
]


if TYPE_CHECKING:  # pragma: no cover - import-time helpers for type checkers only
    from .batch_jobs import run_daily_insights
    from .cache import PromptCache
    from .costs import DailyLimiter, UsageTracker
    from .router import AIResponse, AIRouter
    from .templates import choose_template


def __getattr__(name: str) -> Any:  # pragma: no cover - thin import shim
    if name == "run_daily_insights":
        from .batch_jobs import run_daily_insights as attr

        return attr
    if name == "PromptCache":
        from .cache import PromptCache as attr

        return attr
    if name in {"DailyLimiter", "UsageTracker"}:
        from .costs import DailyLimiter, UsageTracker

        return {"DailyLimiter": DailyLimiter, "UsageTracker": UsageTracker}[name]
    if name in {"AIResponse", "AIRouter"}:
        from .router import AIResponse, AIRouter

        return {"AIResponse": AIResponse, "AIRouter": AIRouter}[name]
    if name == "choose_template":
        from .templates import choose_template as attr

        return attr
    raise AttributeError(name)


def __dir__() -> list[str]:  # pragma: no cover - module introspection helper
    return sorted(__all__)
