from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ..metrics import AI_CACHE_HITS
from ..services.storage import StorageService


@dataclass
class CachedResponse:
    text: str
    model: str
    source: str
    tokens_in: int
    tokens_out: int
    usd_cost: float


class PromptCache:
    """Simple prompt cache backed by the database."""

    def __init__(self, storage: StorageService, ttl_seconds: int) -> None:
        self._storage = storage
        self._ttl_seconds = max(60, ttl_seconds)

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        return " ".join(prompt.strip().lower().split())

    def _cache_key(self, kind: str, prompt: str, locale: str) -> str:
        normalized = self._normalize_prompt(prompt)
        payload = f"{kind}:{locale}:{normalized}"
        return sha256(payload.encode("utf-8")).hexdigest()

    async def get(self, kind: str, prompt: str, locale: str) -> CachedResponse | None:
        cache_key = self._cache_key(kind, prompt, locale)
        entry = await self._storage.get_cache_entry(cache_key)
        if not entry:
            return None
        AI_CACHE_HITS.labels(kind).inc()
        return CachedResponse(
            text=entry.response_text,
            model=entry.model,
            source=entry.source,
            tokens_in=entry.tokens_in,
            tokens_out=entry.tokens_out,
            usd_cost=entry.usd_cost,
        )

    async def set(
        self,
        *,
        kind: str,
        prompt: str,
        locale: str,
        response_text: str,
        model: str,
        source: str,
        tokens_in: int,
        tokens_out: int,
        usd_cost: float,
    ) -> None:
        if len(response_text.strip()) < 60:
            return
        cache_key = self._cache_key(kind, prompt, locale)
        await self._storage.upsert_cache_entry(
            cache_key=cache_key,
            kind=kind,
            locale=locale,
            prompt=prompt,
            response_text=response_text,
            model=model,
            source=source,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            usd_cost=usd_cost,
            ttl_seconds=self._ttl_seconds,
        )
