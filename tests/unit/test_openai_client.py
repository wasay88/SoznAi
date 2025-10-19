from types import SimpleNamespace

import pytest

from backend.app.ai.openai_client import OpenAIClient


@pytest.mark.anyio
async def test_openai_client_offline_stub() -> None:
    client = OpenAIClient(api_key=None)
    text, tokens_in, tokens_out, cost = await client.complete(
        model="gpt-4-mini", prompt="Provide support", max_tokens=120
    )
    assert tokens_in > 0 and tokens_out > 0
    assert cost == 0.0
    assert "офлайн" in text or "offline" in text


class _FakeCompletion:
    def __init__(self) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content="Result"))]
        self.usage = {"prompt_tokens": 12, "completion_tokens": 18}


class _FakeCompletions:
    async def create(self, **kwargs):  # pragma: no cover - simple stub
        return _FakeCompletion()


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


@pytest.mark.anyio
async def test_openai_client_stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAIClient(api_key="fake")
    client._client = _FakeClient()  # type: ignore[attr-defined]
    text, tokens_in, tokens_out, cost = await client.complete(
        model="gpt-4-mini", prompt="Need help", max_tokens=60
    )
    assert text == "Result"
    assert tokens_in == 12 and tokens_out == 18
    assert cost > 0.0
