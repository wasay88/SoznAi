from __future__ import annotations

from backend.app.schemas.webhook import TelegramWebhookUpdate


def test_webhook_parsing_extracts_text_and_chat() -> None:
    payload = {
        "update_id": 123,
        "message": {
            "message_id": 456,
            "text": "Привет, бот!",
            "chat": {"id": 789, "type": "private"},
        },
    }
    update = TelegramWebhookUpdate.model_validate(payload)
    assert update.message_text == "Привет, бот!"
    assert update.chat_id == 789


def test_webhook_parsing_handles_missing_text() -> None:
    payload = {
        "update_id": 789,
        "message": {
            "message_id": 1,
            "chat": {"id": 999},
        },
    }
    update = TelegramWebhookUpdate.model_validate(payload)
    assert update.message_text is None
    assert update.chat_id == 999


def test_webhook_parsing_handles_missing_message() -> None:
    payload = {"update_id": 555}
    update = TelegramWebhookUpdate.model_validate(payload)
    assert update.message_text is None
    assert update.chat_id is None
