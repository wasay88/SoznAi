# backend/main.py  — SoznAi v4.4-pre (safe mode: works with or without BOT_TOKEN)
import os
import threading
import contextlib

# .env подхватываем мягко (не обязателен)
with contextlib.suppress(Exception):
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, JSONResponse

APP_NAME = "SoznAi"
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip() or "soznai_bot"
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
PORT = int(os.getenv("PORT", "10000"))  # Railway/Koyeb ставят PORT

app = FastAPI(title=APP_NAME)
MODE = "offline"  # offline | bot
_bot_thread = None  # type: ignore


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


@app.get("/mode")
def get_mode():
    return {"mode": MODE, "bot_username": BOT_USERNAME if MODE == "bot" else None}


@app.get("/", response_class=PlainTextResponse)
def root():
    hint = (
        f"{APP_NAME} backend running ({MODE}). "
        f"Health: /healthz, Mode: /mode"
    )
    return hint


def _run_bot_polling():
    """Запускаем Telegram-бота в отдельном потоке.
    Пытаемся использовать aiogram 2.x. Если его нет/не та версия — остаёмся offline."""
    try:
        # aiogram 2.x
        from aiogram import Bot, Dispatcher, executor, types  # type: ignore

        bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
        dp = Dispatcher(bot)

        @dp.message_handler(commands=["start", "help"])
        async def _(m: types.Message):
            text = (
                "Привет! Это SoznAi.\n"
                "Открой WebApp: "
                f"{WEBAPP_URL or 'укажи переменную WEBAPP_URL'}"
            )
            await m.answer(text)

        executor.start_polling(dp, skip_updates=True)

    except Exception as e:
        # Если aiogram 3.x или нет aiogram — не валимся, просто лог и offline
        print(f"⚠️ Bot thread stopped: {e}")


def maybe_start_bot():
    global MODE, _bot_thread
    if not BOT_TOKEN:
        MODE = "offline"
        print("⚠️ BOT_TOKEN не найден — работаем в offline-режиме (бот не запущен).")
        return

    # Пробуем импортировать aiogram
    try:
        import aiogram  # noqa: F401
    except Exception as e:
        MODE = "offline"
        print(f"⚠️ aiogram не установлен/несовместим: {e}. Offline-режим.")
        return

    MODE = "bot"
    print("🤖 Запускаю Telegram-бота в отдельном потоке…")
    _bot_thread = threading.Thread(target=_run_bot_polling, daemon=True)
    _bot_thread.start()


def run():
    # Стартуем бот (если возможно)
    maybe_start_bot()

    # Запускаем HTTP-сервер
    import uvicorn
    print(f"✅ {APP_NAME} запущен на 0.0.0.0:{PORT} (mode={MODE})")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    run()
