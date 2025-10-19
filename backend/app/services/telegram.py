# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types.input_file import BufferedInputFile

from ..metrics import WEBHOOK_EVENTS
from ..schemas.webhook import TelegramWebhookUpdate, WebhookResponse
from .modes import ModeManager, ModeState
from .storage import StorageService

if TYPE_CHECKING:
    from ..ai.router import AIRouter

logger = logging.getLogger(__name__)


class TelegramService:
    """Wrapper around aiogram Bot with retry logic and graceful degradation."""

    def __init__(
        self,
        token: str | None,
        webhook_url: str | None,
        *,
        timeout: float,
        retries: int,
        secret_token: str | None = None,
        storage: StorageService | None = None,
        ai_router: AIRouter | None = None,
    ) -> None:
        self._token = token
        self._webhook_url = webhook_url if webhook_url else None
        self._timeout = timeout
        self._retries = retries
        self._secret_token = secret_token
        self._storage = storage
        self._bot: Bot | None = None
        self._ai_router = ai_router

    @property
    def available(self) -> bool:
        return bool(self._token and self._webhook_url)

    def attach_storage(self, storage: StorageService) -> None:
        self._storage = storage

    def attach_ai_router(self, ai_router: AIRouter) -> None:
        self._ai_router = ai_router

    def _timeout_seconds(self, override: float | None = None) -> int:
        value = self._timeout if override is None else override
        return max(1, int(value))

    def _ensure_bot(self) -> Bot:
        if not self._token:
            raise RuntimeError("Telegram bot token is not configured")
        if self._bot is None:
            self._bot = Bot(token=self._token, parse_mode="HTML")
        return self._bot

    async def ensure_webhook(self) -> bool:
        if not self.available:
            logger.warning("Telegram webhook skipped: missing configuration")
            return False

        bot = self._ensure_bot()
        url = str(self._webhook_url)
        timeout_seconds = self._timeout_seconds()

        try:
            info = await bot.get_webhook_info(request_timeout=timeout_seconds)
            if info and info.url == url:
                logger.info("Telegram webhook already configured", extra={"webhook": url})
                return True
        except TelegramNetworkError as exc:
            logger.warning("Unable to fetch current webhook info: %s", exc)
        except TelegramAPIError as exc:
            logger.error("Telegram API error while checking webhook: %s", exc)

        delays = [0.5, 1.0, 2.0]
        for attempt in range(1, self._retries + 1):
            try:
                await bot.set_webhook(
                    url=url,
                    request_timeout=timeout_seconds,
                    secret_token=self._secret_token,
                )
                logger.info("Telegram webhook configured", extra={"webhook": url})
                return True
            except TelegramNetworkError as exc:
                delay_index = min(attempt - 1, len(delays) - 1)
                logger.error(
                    "Telegram webhook attempt %s failed",
                    attempt,
                    extra={"status": "network", "error": str(exc)},
                )
                await asyncio.sleep(delays[delay_index])
            except TelegramRetryAfter as exc:
                delay_index = min(attempt - 1, len(delays) - 1)
                wait_time = float(getattr(exc, "retry_after", delays[delay_index]))
                logger.warning(
                    "Telegram webhook throttled",
                    extra={"status": 429, "error": str(exc)},
                )
                await asyncio.sleep(wait_time)
            except TelegramAPIError as exc:
                logger.error(
                    "Telegram API error configuring webhook",
                    extra={"status": getattr(exc, "error_code", "api"), "error": str(exc)},
                )
                if getattr(exc, "error_code", 500) >= 500:
                    delay_index = min(attempt - 1, len(delays) - 1)
                    await asyncio.sleep(delays[delay_index])
                    continue
                break
            except Exception as exc:
                logger.exception("Unexpected error configuring webhook: %s", exc)
                break
        return False

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        bot = self._ensure_bot()
        delays = [0.5, 1.0, 2.0]
        for attempt in range(1, self._retries + 1):
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    disable_notification=False,
                    request_timeout=self._timeout_seconds(),
                    reply_markup=reply_markup,
                )
                return True
            except TimeoutError as exc:
                delay_index = min(attempt - 1, len(delays) - 1)
                logger.warning(
                    "Send message timeout",
                    extra={"status": "timeout", "error": str(exc), "attempt": attempt},
                )
                await asyncio.sleep(delays[delay_index])
            except TelegramNetworkError as exc:
                delay_index = min(attempt - 1, len(delays) - 1)
                logger.warning(
                    "Send message network error",
                    extra={"status": "network", "error": str(exc), "attempt": attempt},
                )
                await asyncio.sleep(delays[delay_index])
            except TelegramRetryAfter as exc:
                delay_index = min(attempt - 1, len(delays) - 1)
                wait_time = float(getattr(exc, "retry_after", delays[delay_index]))
                logger.warning(
                    "Send message throttled",
                    extra={"status": 429, "error": str(exc), "attempt": attempt},
                )
                await asyncio.sleep(wait_time)
            except TelegramAPIError as exc:
                logger.error(
                    "Telegram API error sending message",
                    extra={
                        "status": getattr(exc, "error_code", "api"),
                        "error": str(exc),
                        "attempt": attempt,
                    },
                )
                if getattr(exc, "error_code", 500) >= 500:
                    delay_index = min(attempt - 1, len(delays) - 1)
                    await asyncio.sleep(delays[delay_index])
                    continue
                break
            except Exception as exc:
                logger.exception("Unexpected error sending telegram message: %s", exc)
                break
        return False

    async def check_readiness(self, *, request_timeout: float = 2.0) -> tuple[bool, str]:
        if not self._token:
            return False, "token not configured"
        if not self._webhook_url:
            return False, "webhook url missing"

        bot = self._ensure_bot()
        try:
            await bot.get_me(request_timeout=self._timeout_seconds(request_timeout))
        except TelegramNetworkError as exc:
            logger.warning(
                "Telegram getMe network error",
                extra={"status": "network", "error": str(exc)},
            )
            return False, "network"
        except TelegramRetryAfter as exc:
            logger.warning(
                "Telegram getMe throttled",
                extra={"status": 429, "error": str(exc)},
            )
            return False, "throttled"
        except TelegramAPIError as exc:
            logger.error(
                "Telegram getMe api error",
                extra={"status": getattr(exc, "error_code", "api"), "error": str(exc)},
            )
            return False, f"api:{getattr(exc, 'error_code', 'unknown')}"
        except Exception as exc:
            logger.exception("Unexpected error during getMe: %s", exc)
            return False, "unexpected"
        return True, "ok"

    async def _resolve_user_id(self, chat_id: int | None) -> int | None:
        if chat_id is None or not self._storage:
            return None
        user = await self._storage.ensure_user_by_telegram(chat_id)
        return user.id

    async def _handle_command(
        self,
        command: str,
        message: str,
        chat_id: int | None,
    ) -> tuple[list[str], InlineKeyboardMarkup | None]:
        storage = self._storage
        user_id = await self._resolve_user_id(chat_id)
        if command == "/start":
            return (
                [
                "Привет! Я SoznAi — помогу отследить эмоции и вести дневник.",
                "Используй /help, чтобы увидеть команды.",
                "Мини-приложение: https://soznai-production.up.railway.app",
                ],
                None,
            )
        if command == "/help":
            return (
                [
                "Доступные команды:",
                "/mood <код> <1-5> [заметка] — сохранить эмоцию.",
                "/journal <текст> — сохранить запись дневника.",
                "/summary — сводка за 7 дней.",
                "/export — CSV за 30 дней.",
                "/delete_me — удалить все данные.",
                ],
                None,
            )
        if command == "/resource":
            if self._ai_router and user_id is not None:
                ai_reply = await self._ai_router.ask(
                    user_id=user_id,
                    kind="breathing_hint",
                    text="Подскажи дыхательную практику",
                )
                return ([ai_reply.text], None)
            return (
                [
                    "Практика дыхания 1-2-3:",
                    "Вдох на 4 счета, задержка 4, выдох 6.",
                    "Повтори 3 цикла и замечай ощущения.",
                ],
                None,
            )
        if command == "/journal":
            note = message.partition(" ")[2].strip()
            if not note:
                return (["Отправь запись в формате: /journal Сегодня я благодарен за…"], None)
            if storage and user_id is not None:
                await storage.add_journal_entry(user_id=user_id, text=note, source="bot")
                return (["Запись дневника сохранена!", note], None)
            return (["Запись получена, но хранилище недоступно."], None)
        if command == "/mood":
            remainder = message.partition(" ")[2].strip()
            if not remainder:
                return (
                    [
                        "Использование: /mood joy 4 короткая заметка",
                        "Выбери код эмоции и интенсивность 1-5.",
                    ],
                    None,
                )
            parts = remainder.split()
            if len(parts) < 2:
                return (["Укажи код эмоции и интенсивность 1-5."], None)
            emotion_code = parts[0]
            try:
                intensity = int(parts[1])
            except ValueError:
                return (["Интенсивность должна быть числом от 1 до 5."], None)
            if intensity < 1 or intensity > 5:
                return (["Интенсивность должна быть от 1 до 5."], None)
            emotion_note: str | None = " ".join(parts[2:]) if len(parts) > 2 else None
            if storage and user_id is not None:
                await storage.add_emotion_entry(
                    user_id=user_id,
                    emotion_code=emotion_code,
                    intensity=intensity,
                    note=emotion_note,
                    source="bot",
                )
                reply = [
                    "Эмоция сохранена!",
                    f"Код: {emotion_code}, интенсивность: {intensity}.",
                ]
                if emotion_note:
                    reply.append(emotion_note)
                return (reply, None)
            return (["Эмоция получена, но хранилище недоступно."], None)
        if command == "/summary" and storage and user_id is not None:
            summary = await storage.analytics_summary(user_id=user_id, days=7)
            top = ", ".join(
                f"{item['code']}: {item['count']}" for item in summary["top_emotions"]
            ) or "нет данных"
            prompt = (
                "Сформируй короткую сводку за 7 дней с поддержкой и предложением шага."
                f" Серия: {summary['streak_days']} дней, записей: {summary['entries_count']},"
                f" средняя интенсивность: {summary['mood_avg'] or 'нет'}, топ эмоции: {top},"
                f" последняя запись: {summary['last_entry_ts'] or 'нет записей'}."
            )
            if self._ai_router:
                ai_reply = await self._ai_router.ask(
                    user_id=user_id,
                    kind="weekly_review",
                    text=prompt,
                )
                return ([ai_reply.text], None)
            mood = summary["mood_avg"] or "N/A"
            last_ts = summary["last_entry_ts"] or "нет записей"
            return (
                [
                    "Сводка за 7 дней:",
                    f"Серия дней: {summary['streak_days']}",
                    f"Записей: {summary['entries_count']}",
                    f"Средняя интенсивность: {mood}",
                    f"Топ эмоции: {top}",
                    f"Последняя запись: {last_ts}",
                ],
                None,
            )
        if command == "/export" and storage and user_id is not None:
            csv_bytes = await storage.export_user_data(user_id=user_id, days=30)
            bot = self._ensure_bot()
            document = BufferedInputFile(csv_bytes, filename="soznai-export.csv")
            try:
                await bot.send_document(chat_id=chat_id, document=document)
                return (["Отправил экспорт за 30 дней."], None)
            except Exception as exc:  # pragma: no cover - network errors
                logger.error("Не удалось отправить экспорт: %s", exc)
                return (["Не удалось отправить файл, попробуй позже."], None)
        if command == "/delete_me" and storage and user_id is not None:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Да", callback_data="delete_confirm"),
                        InlineKeyboardButton(text="Отмена", callback_data="delete_cancel"),
                    ]
                ]
            )
            return (
                [
                    "Удалить все данные?",
                    "Нажми 'Да' для подтверждения или 'Отмена' чтобы прервать.",
                ],
                keyboard,
            )
        return ([], None)

    async def _handle_callback(
        self,
        update: TelegramWebhookUpdate,
    ) -> WebhookResponse:
        data = update.callback_data or ""
        chat_id = update.chat_id
        if update.callback_query:
            try:
                bot = self._ensure_bot()
                await bot.answer_callback_query(update.callback_query.id)
            except Exception as exc:  # pragma: no cover - network
                logger.debug("Failed to answer callback: %s", exc)

        if data == "delete_confirm" and self._storage and chat_id is not None:
            user_id = await self._resolve_user_id(chat_id)
            if user_id is not None:
                await self._storage.delete_user(user_id)
            text = "Твои данные удалены. Мы будем рады видеть тебя снова."
        elif data == "delete_cancel":
            text = "Удаление отменено."
        else:
            text = "Действие не поддерживается."

        delivered = False
        if chat_id is not None:
            delivered = await self._send_message(chat_id, text)
        if delivered:
            WEBHOOK_EVENTS.labels(result="delivered").inc()
        else:
            WEBHOOK_EVENTS.labels(result="failed").inc()
        return WebhookResponse(response=text, delivered=delivered)

    async def process_update(
        self,
        update: TelegramWebhookUpdate,
        mode_manager: ModeManager,
    ) -> WebhookResponse:
        status = mode_manager.snapshot()
        message = update.message_text or ""
        chat_id = update.chat_id

        if update.callback_data:
            return await self._handle_callback(update)

        response_lines = [
            "Привет! Я SoznAi — помощник самоосознанности.",
            f"Сейчас режим: {status.state.value}.",
        ]

        command = message.split()[0] if message.startswith("/") else None
        if command:
            command_lines, reply_markup = await self._handle_command(command, message, chat_id)
            if command_lines:
                response_lines = list(command_lines)
            else:
                response_lines.append("Команда не распознана, попробуй /help.")
            markup = reply_markup
        else:
            markup = None
            if message:
                response_lines.append(f"Ты написал: {message}")
                if self._storage and chat_id is not None:
                    user_id = await self._resolve_user_id(chat_id)
                    if user_id is not None:
                        await self._storage.add_journal_entry(
                            user_id=user_id,
                            text=message,
                            source="bot",
                        )
                        response_lines.append("Запись добавлена в дневник.")
                        if self._ai_router:
                            ai_reply = await self._ai_router.ask(
                                user_id=user_id,
                                kind="mood_reply",
                                text=message,
                            )
                            response_lines.append(ai_reply.text)
            if status.state == ModeState.OFFLINE:
                response_lines.append("Я в офлайне, но дыхательная практика доступна в вебе.")
            elif status.state == ModeState.DEGRADED:
                response_lines.append("Некоторые возможности ограничены, проверяю подключение.")
            else:
                response_lines.append("Готов отслеживать твое состояние. Используй /help.")

        response_text = "\n".join(filter(None, response_lines))
        if chat_id is None:
            logger.debug("Webhook update без chat id; ответ только в API")
            WEBHOOK_EVENTS.labels(result="no_chat").inc()
            return WebhookResponse(response=response_text, delivered=False)

        delivered = await self._send_message(
            chat_id,
            response_text,
            reply_markup=markup if command else None,
        )
        if not delivered:
            await mode_manager.set_degraded("failed to deliver telegram message")
            WEBHOOK_EVENTS.labels(result="failed").inc()
            return WebhookResponse(response=response_text, delivered=False)

        WEBHOOK_EVENTS.labels(result="delivered").inc()
        return WebhookResponse(response=response_text, delivered=True)

    async def close(self) -> None:
        if self._bot:
            await self._bot.session.close()
            self._bot = None
