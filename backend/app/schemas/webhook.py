from __future__ import annotations

from pydantic import BaseModel, Field


class TelegramChat(BaseModel):
    id: int
    type: str | None = None


class TelegramMessage(BaseModel):
    message_id: int = Field(..., alias="message_id")
    text: str | None = None
    chat: TelegramChat | None = None


class TelegramCallbackQuery(BaseModel):
    id: str
    data: str | None = None
    message: TelegramMessage | None = None


class TelegramWebhookUpdate(BaseModel):
    update_id: int = Field(..., alias="update_id")
    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = Field(default=None, alias="callback_query")

    @property
    def message_text(self) -> str | None:
        if self.message and self.message.text:
            return self.message.text
        if self.callback_query and self.callback_query.message:
            return self.callback_query.message.text
        return None

    @property
    def chat_id(self) -> int | None:
        if self.message and self.message.chat:
            return self.message.chat.id
        if self.callback_query and self.callback_query.message and self.callback_query.message.chat:
            return self.callback_query.message.chat.id
        return None

    @property
    def callback_data(self) -> str | None:
        if self.callback_query:
            return self.callback_query.data
        return None


class WebhookResponse(BaseModel):
    response: str
    delivered: bool = False
