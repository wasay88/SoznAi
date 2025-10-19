from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.app.ai.router import AIResponse
from backend.app.schemas.webhook import TelegramWebhookUpdate
from backend.app.services.storage import StorageService
from backend.app.services.telegram import TelegramService
from backend.db import create_engine, create_session_factory, init_db


class StubRouter:
    async def ask(
        self,
        *,
        user_id: int | None,
        kind: str,
        text: str,
        locale: str = "ru",
        use_cache: bool = True,
    ) -> AIResponse:
        return AIResponse(
            text="AI summary",
            source="turbo",
            model="gpt-turbo",
            tokens_in=10,
            tokens_out=20,
            usd_cost=0.01,
        )


@pytest.mark.anyio
async def test_telegram_summary_uses_ai(tmp_path) -> None:
    db_path = tmp_path / "bot.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_db(engine, session_factory, "test", database_url)

    storage = StorageService(session_factory)
    user = await storage.ensure_user_by_telegram(55)
    await storage.add_emotion_entry(
        user_id=user.id,
        emotion_code="joy",
        intensity=4,
        note=None,
        source="test",
    )

    service = TelegramService(
        token=None,
        webhook_url=None,
        timeout=1.0,
        retries=1,
        storage=storage,
        ai_router=StubRouter(),
    )

    lines, markup = await service._handle_command("/summary", "/summary", chat_id=55)
    assert lines == ["AI summary"]
    assert markup is None

    await engine.dispose()


@pytest.mark.anyio
async def test_telegram_delete_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(token=None, webhook_url=None, timeout=1.0, retries=1, storage=None)
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))
    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 10,
            "callback_query": {
                "id": "cb1",
                "data": "delete_cancel",
                "message": {
                    "message_id": 1,
                    "chat": {"id": 7},
                    "text": "Удалить?",
                },
            },
        }
    )
    response = await service._handle_callback(update)
    assert response.response == "Удаление отменено."
