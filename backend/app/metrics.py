from __future__ import annotations

try:  # pragma: no cover - optional dependency for lightweight testing environments
    from prometheus_client import Counter, Histogram
except ModuleNotFoundError:  # pragma: no cover - fallback no-op metrics
    class _NoopMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

    def Counter(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

    def Histogram(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

REQUEST_COUNT = Counter(
    "soznai_requests_total",
    "Total HTTP requests processed by SoznAi",
    ("method", "path", "status"),
)

REQUEST_LATENCY = Histogram(
    "soznai_request_latency_seconds",
    "HTTP request latency in seconds",
    ("method", "path"),
)

REQUEST_ERRORS = Counter(
    "soznai_request_errors_total",
    "HTTP requests resulting in server errors",
    ("method", "path", "status"),
)

USER_API_COUNTER = Counter(
    "soznai_user_api_hits_total",
    "Authenticated API hits per endpoint",
    ("endpoint",),
)

WEBHOOK_EVENTS = Counter(
    "soznai_webhook_events_total",
    "Telegram webhook events processed",
    ("result",),
)

AI_REQUESTS = Counter(
    "soznai_ai_requests_total",
    "AI routed requests",
    ("source", "kind", "model"),
)

AI_TOKENS = Counter(
    "soznai_ai_tokens_total",
    "Tokens consumed by AI requests",
    ("direction",),
)

AI_COST = Counter(
    "soznai_ai_cost_usd_total",
    "Accumulated USD cost of AI requests",
)

AI_CACHE_HITS = Counter(
    "soznai_ai_cache_hits_total",
    "Number of cache hits for AI responses",
    ("kind",),
)

__all__ = [
    "AI_CACHE_HITS",
    "AI_COST",
    "AI_REQUESTS",
    "AI_TOKENS",
    "REQUEST_COUNT",
    "REQUEST_ERRORS",
    "REQUEST_LATENCY",
    "USER_API_COUNTER",
    "WEBHOOK_EVENTS",
]
