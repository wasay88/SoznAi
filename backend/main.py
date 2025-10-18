from fastapi import FastAPI, Request
import os
import httpx

app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")

@app.get("/healthz")
def health():
    return "ok"

@app.get("/mode")
def mode():
    if BOT_TOKEN:
        return {"mode": "bot", "bot_username": "soznai_bot"}
    return {"mode": "offline"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", {}).get("text", "")
    chat_id = data.get("message", {}).get("chat", {}).get("id")
    if not chat_id:
        return {"ok": True}
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": f"Ты написал: {message} 💬"}
        )
    return {"ok": True}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
