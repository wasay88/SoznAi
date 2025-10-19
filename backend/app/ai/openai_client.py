from __future__ import annotations

import asyncio

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency
    AsyncOpenAI = None  # type: ignore

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.0005, 0.0015),
}


class OpenAIClient:
    """Thin wrapper above the OpenAI async SDK with graceful degradation."""

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key
        self._client = AsyncOpenAI(api_key=api_key) if api_key and AsyncOpenAI else None

    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
    ) -> tuple[str, int, int, float]:
        """Return text, prompt tokens, completion tokens, cost."""

        tokens_in = max(1, int(len(prompt.split()) * 1.2))
        tokens_out = max(20, min(max_tokens, int(max_tokens * 0.6)))
        cost = self._estimate_cost(model, tokens_in, tokens_out)

        if not self._client:
            # Offline stub keeps integration working without network access
            response = (
                "Я офлайн, но поддерживаю тебя: представь, что ты уже нашёл нужные слова."
                if model.startswith("gpt")
                else "SoznAi companion is offline — focus on your breath for a moment."
            )
            await asyncio.sleep(0)  # yield control
            return response, tokens_in, tokens_out, 0.0

        completion = await self._client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise, empathetic wellbeing companion.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        message = completion.choices[0].message.content or ""
        usage = completion.usage or {}
        tokens_in = int(usage.get("prompt_tokens", tokens_in))
        tokens_out = int(usage.get("completion_tokens", tokens_out))
        cost = self._estimate_cost(model, tokens_in, tokens_out)
        return message.strip(), tokens_in, tokens_out, cost

    @staticmethod
    def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            # Default rough estimate
            return round((tokens_in + tokens_out) / 1000 * 0.0005, 6)
        in_price, out_price = pricing
        return round(tokens_in / 1000 * in_price + tokens_out / 1000 * out_price, 6)
