import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8080")
BOT_USERNAME = os.getenv("BOT_USERNAME", "soznai_bot")
PORT = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN:
    raise RuntimeError("Укажи BOT_TOKEN в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SUBSCRIBERS = set()
REMINDER_HOURS = {9, 21}

@dp.message(CommandStart())
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Open SoznAi", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )
    await message.answer(
        f"Привет. Это @{BOT_USERNAME}. Открой SoznAi и сделай один маленький шаг. "
        "Команды: /remind_on, /remind_off",
        reply_markup=kb
    )

@dp.message(Command("remind_on"))
async def remind_on(message: types.Message):
    SUBSCRIBERS.add(message.chat.id)
    await message.answer("Напоминания включены. Пишу в 09:00 и 21:00 (время сервера).")

@dp.message(Command("remind_off"))
async def remind_off(message: types.Message):
    SUBSCRIBERS.discard(message.chat.id)
    await message.answer("Напоминания выключены.")

async def reminder_loop():
    last_sent = set()
    while True:
        now = datetime.now()
        key = (now.date().isoformat(), now.hour)
        if now.minute == 0 and now.hour in REMINDER_HOURS and key not in last_sent:
            last_sent.add(key)
            for chat_id in list(SUBSCRIBERS):
                try:
                    txt = "🌿 Проверь дыхание. Оцени по шкале 0–10 и сделай один шаг." if now.hour == 9 else "☀ Вечерний чек‑ин: какая цифра сейчас?"
                    await bot.send_message(chat_id, txt)
                except Exception:
                    pass
        await asyncio.sleep(30)

BASE_DIR = os.path.dirname(__file__)
FRONT = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))

async def index(request):
    with open(os.path.join(FRONT, "index.html"), "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")

async def assets(request):
    path = request.match_info.get("path")
    full = os.path.join(FRONT, "assets", path)
    if not os.path.exists(full):
        raise web.HTTPNotFound()
    return web.FileResponse(full)

async def locales(request):
    path = request.match_info.get("name")
    full = os.path.join(FRONT, "locales", path)
    if not os.path.exists(full):
        raise web.HTTPNotFound()
    return web.FileResponse(full)

async def run_web():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/assets/{path:.*}", assets)
    app.router.add_get("/locales/{name:.*}", locales)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"SoznAi web running at http://localhost:{PORT}")

async def main():
    await asyncio.gather(
        run_web(),
        reminder_loop(),
        dp.start_polling(bot),
    )

if __name__ == "__main__":
    asyncio.run(main())
