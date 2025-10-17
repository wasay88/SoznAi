# SoznAi — MVP (Reminders + PDF + Garden + Emotion Scale + RU/EN/UA i18n + Auto-Locale)

Новое в версии:
- 🌍 Три локали: RU / EN / UA (uk).
- 🤖 Автодетект языка из `Telegram.WebApp.initDataUnsafe.user.language_code` (fallback на язык браузера).
- 🔔 Напоминания (`/remind_on`, `/remind_off`), 🧾 PDF‑экспорт, 🌱 «Сад защит», 🌡️ Шкала эмоций 0–10.
- 🤖 Имя бота задаётся через `.env` (`BOT_USERNAME`), по умолчанию `soznai_bot`.

## Быстрый старт
1) Создай `.env` из `.env.example` и вставь `BOT_TOKEN` (НЕ присылай его мне или в публичные места):

```
BOT_TOKEN=ВашТокенИзBotFather
BOT_USERNAME=soznai_bot
WEBAPP_URL=http://localhost:8080
PORT=8080
```

2) Запусти backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
3) Открой `http://localhost:8080`. Для Telegram мини‑приложения: `ngrok http 8080` → URL в @BotFather → `/setmenubutton` → Web App.

