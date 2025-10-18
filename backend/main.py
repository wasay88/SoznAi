from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os, json, httpx, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONT = ROOT / "frontend"

app = FastAPI(title="SoznAi")

# статика под /static
app.mount("/static", StaticFiles(directory=str(FRONT), html=False), name="static")

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")

@app.get("/")
def index():
    return FileResponse(str(FRONT / "index.html"))

@app.get("/healthz")
def health():
    return {"status": "ok", "version": os.getenv("VERSION", "0.1.0")}

@app.get("/mode")
def mode():
    if BOT_TOKEN:
        return {"mode": "bot", "bot_username": "soznai_bot"}
    return {"mode": "offline"}

# --- Мини-API
@app.post("/api/v1/journal")
async def journal(request: Request):
    data = await request.json()
    text = data.get("text","").strip()
    # MVP: просто подтверждаем приём; хранилище подключим позже
    return {"ok": bool(text)}

@app.post("/webhook")
async def webhook(request: Request):
    # простая проверка секрета (если используете X-Telegram-Bot-Api-Secret-Token)
    # tg_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    # if tg_secret and tg_secret != WEBHOOK_SECRET:
    #     return JSONResponse({"ok": False}, status_code=401)

    body = await request.json()
    msg = body.get("message", {})
    text = msg.get("text", "")
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not (BOT_TOKEN and chat_id):
        return {"ok": True}

    reply = f"Ты написал: {text} 💬"
    async with httpx.AsyncClient(timeout=8) as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": reply}
        )
    return {"ok": True}
