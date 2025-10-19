from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramRetryAfter

from backend.app.schemas.webhook import TelegramWebhookUpdate
from backend.app.services.modes import ModeManager, ModeState
from backend.app.services.storage import StorageService
from backend.app.services.telegram import TelegramService


class DummyTelegramNetworkError(TelegramNetworkError):
    def __init__(self) -> None:  # pragma: no cover
        Exception.__init__(self, "network")
        self.method = SimpleNamespace(name="dummy")
        self.message = "network"


def _service_with_storage() -> tuple[TelegramService, StorageService]:
    storage = AsyncMock(spec=StorageService)
    storage.ensure_user_by_telegram = AsyncMock(return_value=SimpleNamespace(id=1))
    storage.analytics_summary = AsyncMock(
        return_value={
            "streak_days": 1,
            "entries_count": 2,
            "mood_avg": 3.0,
            "top_emotions": [{"code": "joy", "count": 1}],
            "last_entry_ts": "2024-01-01T00:00:00",
        }
    )
    storage.export_user_data = AsyncMock(return_value=b"type,created_at")
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=1.0,
        retries=1,
        storage=storage,
    )
    return service, storage


@pytest.mark.anyio
async def test_process_update_records_plain_message(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")

    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "_send_message", sender)

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "text": "Сегодня было спокойно",
                "chat": {"id": 123},
            },
        }
    )

    result = await service.process_update(update, mode_manager)

    sender.assert_awaited_once()
    storage.add_journal_entry.assert_awaited_once()
    assert "Запись добавлена" in result.response
    assert mode_manager.snapshot().state == ModeState.ONLINE


@pytest.mark.anyio
async def test_help_command_returns_description(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 2,
            "message": {
                "message_id": 2,
                "text": "/help",
                "chat": {"id": 456},
            },
        }
    )

    result = await service.process_update(update, mode_manager)

    storage.add_journal_entry.assert_not_called()
    assert "Доступные команды" in result.response


@pytest.mark.anyio
async def test_resource_command(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 21,
            "message": {
                "message_id": 21,
                "text": "/resource",
                "chat": {"id": 789},
            },
        }
    )

    result = await service.process_update(update, mode_manager)

    assert "Практика" in result.response
    storage.add_journal_entry.assert_not_called()


@pytest.mark.anyio
async def test_journal_command_without_text(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 3,
            "message": {
                "message_id": 3,
                "text": "/journal",
                "chat": {"id": 789},
            },
        }
    )

    result = await service.process_update(update, mode_manager)

    storage.add_journal_entry.assert_not_called()
    assert "формате" in result.response


@pytest.mark.anyio
async def test_journal_command_with_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 4,
            "message": {
                "message_id": 4,
                "text": "/journal Спасибо за поддержку",
                "chat": {"id": 321},
            },
        }
    )

    result = await service.process_update(update, mode_manager)

    storage.add_journal_entry.assert_awaited_once()
    assert "сохранена" in result.response


@pytest.mark.anyio
async def test_mood_command_invalid_intensity(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 5,
            "message": {
                "message_id": 5,
                "text": "/mood joy сильная",
                "chat": {"id": 600},
            },
        }
    )

    result = await service.process_update(update, mode_manager)

    storage.add_emotion_entry.assert_not_called()
    assert "числом" in result.response


@pytest.mark.anyio
async def test_mood_command_stores_emotion(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")

    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 6,
            "message": {
                "message_id": 6,
                "text": "/mood joy 5 вечер",
                "chat": {"id": 55},
            },
        }
    )

    await service.process_update(update, mode_manager)

    storage.add_emotion_entry.assert_awaited_once()
    args = storage.add_emotion_entry.await_args.kwargs
    assert args["emotion_code"] == "joy"
    assert args["intensity"] == 5
    assert args["user_id"] == 1


@pytest.mark.anyio
async def test_summary_command(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 7,
            "message": {"message_id": 7, "text": "/summary", "chat": {"id": 42}},
        }
    )

    result = await service.process_update(update, mode_manager)

    storage.analytics_summary.assert_awaited_once()
    assert "Сводка" in result.response


@pytest.mark.anyio
async def test_export_command(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")

    bot_mock = AsyncMock()
    bot_mock.send_document = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "_ensure_bot", lambda: bot_mock)
    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 8,
            "message": {"message_id": 8, "text": "/export", "chat": {"id": 77}},
        }
    )

    result = await service.process_update(update, mode_manager)

    storage.export_user_data.assert_awaited_once()
    bot_mock.send_document.assert_awaited_once()
    assert "Отправил" in result.response


@pytest.mark.anyio
async def test_process_update_marks_degraded_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=1.0,
        retries=1,
    )
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")

    sender = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "_send_message", sender)

    update = TelegramWebhookUpdate.model_validate(
        {"update_id": 7, "message": {"message_id": 7, "text": "hi", "chat": {"id": 123}}}
    )

    result = await service.process_update(update, mode_manager)

    sender.assert_awaited_once()
    assert result.delivered is False
    assert mode_manager.snapshot().state == ModeState.DEGRADED


@pytest.mark.anyio
async def test_offline_plain_message(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_offline("manual")

    monkeypatch.setattr(service, "_send_message", AsyncMock(return_value=True))

    update = TelegramWebhookUpdate.model_validate(
        {
            "update_id": 9,
            "message": {
                "message_id": 9,
                "text": "привет",
                "chat": {"id": 10},
            },
        }
    )

    result = await service.process_update(update, mode_manager)

    assert "офлайне" in result.response
    storage.add_journal_entry.assert_awaited_once()


@pytest.mark.anyio
async def test_update_without_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    service, storage = _service_with_storage()
    mode_manager = ModeManager()
    await mode_manager.set_online("ready")
    monkeypatch.setattr(service, "_send_message", AsyncMock())

    update = TelegramWebhookUpdate.model_validate(
        {"update_id": 10, "message": {"message_id": 10, "text": "привет"}}
    )

    result = await service.process_update(update, mode_manager)

    storage.add_journal_entry.assert_not_called()
    assert result.delivered is False


@pytest.mark.anyio
async def test_ensure_webhook_retries_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=1.0,
        retries=2,
    )
    bot = AsyncMock()
    bot.get_webhook_info.return_value = SimpleNamespace(url="https://other")
    bot.set_webhook.side_effect = [
        DummyTelegramNetworkError(),
        None,
    ]
    monkeypatch.setattr(service, "_ensure_bot", lambda: bot)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    result = await service.ensure_webhook()

    assert result is True
    assert bot.set_webhook.await_count == 2


@pytest.mark.anyio
async def test_check_readiness_success(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=1.0,
        retries=1,
    )
    bot = AsyncMock()
    bot.get_me.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(service, "_ensure_bot", lambda: bot)

    ok, detail = await service.check_readiness(request_timeout=0.1)

    assert ok is True
    assert detail == "ok"
    bot.get_me.assert_awaited_once()


@pytest.mark.anyio
async def test_check_readiness_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=1.0,
        retries=1,
    )
    bot = AsyncMock()
    bot.get_me.side_effect = DummyTelegramNetworkError()
    monkeypatch.setattr(service, "_ensure_bot", lambda: bot)

    ok, detail = await service.check_readiness(request_timeout=0.1)

    assert ok is False
    assert detail == "network"


@pytest.mark.anyio
async def test_ensure_webhook_handles_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=0.5,
        retries=2,
    )
    bot = AsyncMock()
    bot.get_webhook_info.return_value = SimpleNamespace(url="https://other")
    retry_exc = TelegramRetryAfter(
        method=SimpleNamespace(name="setWebhook"),
        message="429",
        retry_after=0.01,
    )
    bot.set_webhook.side_effect = [retry_exc, None]
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)
    monkeypatch.setattr(service, "_ensure_bot", lambda: bot)

    result = await service.ensure_webhook()

    assert result is True
    assert sleep_mock.await_count == 1
    assert bot.set_webhook.await_count == 2


@pytest.mark.anyio
async def test_send_message_retries_on_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=0.5,
        retries=2,
    )
    bot = AsyncMock()
    api_error = TelegramAPIError(
        method=SimpleNamespace(name="sendMessage"),
        message="server error",
    )
    api_error.error_code = 500
    bot.send_message.side_effect = [api_error, None]
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)
    monkeypatch.setattr(service, "_ensure_bot", lambda: bot)

    ok = await service._send_message(chat_id=1, text="hi")

    assert ok is True
    assert sleep_mock.await_count == 1
    assert bot.send_message.await_count == 2


@pytest.mark.anyio
async def test_send_message_stops_on_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(
        token="token",
        webhook_url="https://example.com",
        timeout=0.5,
        retries=2,
    )
    bot = AsyncMock()
    api_error = TelegramAPIError(
        method=SimpleNamespace(name="sendMessage"),
        message="bad request",
    )
    api_error.error_code = 400
    bot.send_message.side_effect = api_error
    monkeypatch.setattr(service, "_ensure_bot", lambda: bot)

    ok = await service._send_message(chat_id=1, text="hi")

    assert ok is False
    assert bot.send_message.await_count == 1
