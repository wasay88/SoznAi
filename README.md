# SoznAi v6.0

SoznAi v6.0 — автономный компаньон: FastAPI + Telegram-бот + мини-приложение на Railway с аккаунтами, аналитикой и гибридным AI-маршрутизатором.
Продакшен-сайт: <https://soznai-production.up.railway.app>, бот: [@soznai_bot](https://t.me/soznai_bot).

## Возможности

- FastAPI backend с маршрутами `/healthz`, `/readyz`, `/metrics`, `/api/v1/*`, `/api/v1/ai/*`, `/auth/verify` и автоматической инициализацией БД.
- AI-компаньон: `/api/v1/ai/ask`, `/api/v1/ai/limits`, админ-эндпоинты `/api/v1/admin/ai/*`, гибридный роутер (templates → mini → turbo → local) с бюджетами и кэшем.
- Ночные батчи `/api/v1/admin/run/daily` создают инсайты, доступные через `/api/v1/insights` и мини-приложение.
- Версионированные API `/api/v1/journal`, `/api/v1/emotions`, `/api/v1/analytics/summary`, `/api/v1/auth/magiclink`, `/api/v1/me` для персонифицированных данных.
- Telegram-бот на aiogram: команды `/start`, `/help`, `/mood`, `/journal`, `/resource`, `/summary`, `/export`, `/delete_me` с inline-подтверждением удаления.
- Telegram webhook автоматически настраивается и защищён заголовком `X-Telegram-Bot-Api-Secret-Token`.
- Mini App (HTML/CSS/JS) с дыханием, эмоциями, дневником, дашбордом и RU/EN локализацией; поддержка Telegram WebApp API.
- Offline fallback: при отсутствии `BOT_TOKEN` сервис стартует, веб-приложение и API остаются доступны.
- CI/CD GitHub Actions → Railway: Ruff, ESLint, mypy, pytest с покрытием ≥ 85 %, Docker build, smoke-тесты и 60 повторов health-check.

## Структура проекта

```
backend/
  app/
    api/v1/routes.py      # /api/v1/journal, /api/v1/emotions, /api/v1/mode, /api/v1/webhook
    core/                 # конфигурация, логирование, безопасность
    db/                   # SQLAlchemy модели и инициализация
    services/             # ModeManager, TelegramService, StorageService
    schemas/              # Pydantic-схемы API
    main.py               # FastAPI + lifespan (webhook, БД)
frontend/
  index.html, app.js, styles.css, locales/ru.json, locales/en.json
.github/workflows/deploy.yml
Dockerfile, docker-compose.yml, requirements.txt, requirements-dev.txt
```

## Быстрый старт

### Docker Compose

```bash
docker compose up --build
```

После сборки API доступно на `http://localhost:8000`, фронтенд — `http://localhost:8080`.

### Локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
npm install
uvicorn backend.app.main:app --reload
```

Создайте `.env` (не коммитится):

```
BOT_TOKEN=8434647359:AAH0WQKyPVL33kno8lO7V0beWt39XP9BQJA
WEBAPP_URL=https://soznai-production.up.railway.app/webhook
WEBHOOK_SECRET=soznai_secret
DATABASE_URL=sqlite+aiosqlite:///./data/soznai.db
VERSION=6.0.0
ADMIN_TOKEN=change-me
OPENAI_API_KEY=your-openai-key
OPENAI_MODEL_PRIMARY=gpt-4-mini
OPENAI_MODEL_DEEP=gpt-4-turbo
OPENAI_DAILY_LIMIT_USD=0.50
OPENAI_SOFT_LIMIT_USD=0.35
OPENAI_ENABLE_BATCH=false
AI_ROUTER_MODE=auto
AI_CACHE_TTL_SEC=86400
AI_MAX_TOKENS_QUICK=120
AI_MAX_TOKENS_DEEP=400
```

При запуске без `BOT_TOKEN` сервер логирует `mode=offline`, но фронтенд и API остаются активны.

## API

- `GET /healthz` — состояние сервиса, версия и режим.
- `GET /mode` — публичный статус режима.
- `GET /api/v1/mode` / `POST /api/v1/mode` — чтение/переключение режима.
- `POST /webhook`, `POST /api/v1/webhook` — обработчик Telegram (требует `X-Telegram-Bot-Api-Secret-Token`).
- `POST /api/v1/journal` — добавить запись дневника (`text`, опционально `user_id`, `source`).
- `GET /api/v1/journal` — последние записи (по умолчанию до 20).
- `POST /api/v1/emotions` — сохранить эмоцию (`emotion_code`, `intensity`, `note`).
- `GET /api/v1/emotions` — последние эмоции.

## База данных и миграции

- По умолчанию используется SQLite `sqlite+aiosqlite:///./data/soznai.db`. Для PostgreSQL задайте
  `DATABASE_URL=postgresql://user:password@host:5432/soznai` — приложение автоматически
  преобразует его в асинхронный драйвер `postgresql+asyncpg://…`.
- При старте сервиса автоматически запускаются Alembic-миграции (`alembic upgrade head`) и
  создаются таблицы `journal`, `emotions`, `settings`.
- Для ручного применения миграций:

  ```bash
  alembic upgrade head
  ```

- Перенос данных с SQLite на PostgreSQL:

  ```bash
  # 1. Экспорт из SQLite в JSON
  python make/db_export_sqlite.py --sqlite-url sqlite:///./data/soznai.db --output data/export.json

  # 2. Импорт в PostgreSQL (psycopg)
  python make/db_import_postgres.py --input data/export.json \
    --database-url postgresql+psycopg://user:password@host:5432/soznai
  ```

- Резервную копию можно импортировать повторно: ключи `settings` обновляются за счёт `ON CONFLICT`.

### Пример ручного вызова webhook

```bash
curl -X POST https://soznai-production.up.railway.app/api/v1/webhook \
  -H 'Content-Type: application/json' \
  -H 'X-Telegram-Bot-Api-Secret-Token: soznai_secret' \
  -d '{"update_id":1,"message":{"message_id":1,"chat":{"id":123456},"text":"/mood joy 4"}}'
```

## Telegram-бот

- `/start` и `/help` — приветствие и список команд.
- `/mood joy 4 спасибо` — сохраняет эмоцию (`joy`, интенсивность `4`, заметка `спасибо`).
- `/journal Сегодня я благодарен солнцу` — добавляет запись в дневник.
- `/resource` — дыхательное упражнение 1-2-3.
- Любой текст без команды → запись дневника + подсказка.

## Frontend (Mini App)

- Табы «Ресурс», «Эмоции», «Дневник», «Смысл» с RU/EN локализацией.
- Дыхательная практика с циклом из трёх шагов и автовыходом после 3 циклов.
- Формы отправки эмоций и дневника → API, список последних записей.
- Кнопка «Отправить боту» обращается к `/webhook`: при защите webhook сообщает о необходимости написать @soznai_bot напрямую.
- Поддержка Telegram WebApp API (`Telegram.WebApp.ready()` + `expand()`).

## Тесты и качество

```bash
ruff check
npm run lint
pytest --cov=backend --cov-report=term --cov-report=xml --cov-report=html --cov-fail-under=85
```

CI выполняет те же шаги, загружает `htmlcov/` как артефакт, затем собирает Docker-образ и делает smoke-тесты:

```bash
curl -f http://127.0.0.1:8000/healthz
curl -f http://127.0.0.1:8000/api/v1/mode
curl -f http://127.0.0.1:8000/api/v1/journal
curl -f http://127.0.0.1:8000/api/v1/emotions
```

После деплоя workflow ждёт, пока `https://soznai-production.up.railway.app/healthz` вернёт `{"status":"ok"}` (до 60 попыток).

## Observability & Hardening

- **Readiness** — проверяет БД и Telegram:

  ```bash
  curl -s https://soznai-production.up.railway.app/readyz | jq
  # {"ready":true,"db":{"ok":true,"detail":"ok"},"tg":{"ok":true,"detail":"ok"}}
  ```

- **Метрики Prometheus** — счётчики, ошибки, гистограммы латентности:

  ```bash
  curl -s https://soznai-production.up.railway.app/metrics | head
  # soznai_requests_total{method="GET",path="/healthz",status="200"} 12.0
  ```

- **AI метрики** — `soznai_ai_requests_total`, `soznai_ai_tokens_total`, `soznai_ai_cost_usd_total`, `soznai_ai_cache_hits_total`.

- **Структурированные логи** — JSON с ключами `ts`, `level`, `path`, `method`, `status`, `duration_ms`, `request_id`:

  ```json
  {"ts":"2024-05-01T10:00:00+00:00","level":"INFO","logger":"soznai.request","message":"request complete","path":"/healthz","method":"GET","status":200,"duration_ms":2.3,"request_id":"d0b1..."}
  ```

- **Защищённый webhook** — 401 при отсутствии корректного секрета:

  ```bash
  curl -i -X POST https://soznai-production.up.railway.app/webhook -d '{}' \
    -H 'Content-Type: application/json'
  # HTTP/1.1 401 Unauthorized
  ```

### Admin panel & cost controls

- **Доступ** — откройте `https://soznai-production.up.railway.app/admin`, введите `ADMIN_TOKEN`; UI хранит токен в `localStorage` и
  отправляет запросы с заголовком `Authorization: Bearer …`.
- **Обзор** — карточки показывают расход за сегодня, активный режим маршрутизатора, лимиты и hit-rate кэша.
- **Графики** — Chart.js визуализирует стоимость по дням (7/30), токены по модели и распределение запросов по типам.
- **История** — таблица последних 50 обращений (`source` → 💡 template / ⚡ mini / ✨ turbo / ♻️ cache / 🔹 local).
- **Управление** — формы `Soft/Hard limit`, переключатель режима, тумблер ночного батча и кнопка «Остановить GPT» → `mode=local_only`.

Примеры запросов:

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://soznai-production.up.railway.app/api/v1/admin/ai/stats | jq

curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://soznai-production.up.railway.app/api/v1/admin/ai/history?limit=10 | jq

curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"soft":0.02,"hard":0.05}' \
  https://soznai-production.up.railway.app/api/v1/admin/ai/limits
```

## v6.0 Features & How to Verify

1. **Аккаунты и аутентификация** — Telegram ID автоматически привязывается к пользователю; `POST /api/v1/auth/magiclink {"email": ...}` выдаёт ссылку, `/auth/verify?token=...` устанавливает cookie `soz_session`.
2. **AI-компаньон** — `POST /api/v1/ai/ask` маршрутизирует запрос (template → mini → turbo → local) с учётом бюджетов, `/api/v1/ai/limits` и `/api/v1/admin/ai/*` управляют лимитами и режимами.
3. **Кэш и стоимость** — повторный `POST /api/v1/ai/ask` с тем же текстом возвращает `source="cache"`, `/metrics` показывает `soznai_ai_cost_usd_total`.
4. **Ночные инсайты** — `POST /api/v1/admin/run/daily` записывает инсайты, проверка `GET /api/v1/insights` и вкладка «Компаньон» в мини-приложении.
5. **Персонифицированное хранилище** — `/api/v1/journal`, `/api/v1/emotions`, `GET /api/v1/me/export`, `DELETE /api/v1/me` работают для текущего пользователя (заголовок `X-Soznai-Tg-Id` или cookie).
6. **Бот-команды** — `/summary`, `/export`, `/delete_me` (inline подтверждение) дополняют `/start`, `/help`, `/mood`, `/journal`, `/resource`; произвольные сообщения сохраняются и получают AI-ответ.
7. **Наблюдаемость** — `/readyz` валидирует БД и Telegram, `/metrics` содержит `soznai_ai_*`, `/api/v1/analytics/summary` и `/api/v1/ai/ask` должны отвечать после деплоя.

   ```bash
   curl -s https://soznai-production.up.railway.app/healthz
   curl -s https://soznai-production.up.railway.app/readyz
   curl -s -H 'X-Soznai-Tg-Id: 123456' https://soznai-production.up.railway.app/api/v1/analytics/summary
   ```

## Переменные окружения

| Переменная       | Назначение                                                |
| ---------------- | --------------------------------------------------------- |
| `BOT_TOKEN`      | Токен Telegram-бота                                       |
| `WEBAPP_URL`     | Публичный URL бэкенда (без `/webhook` добавляется автоматически) |
| `WEBHOOK_SECRET` | Секрет для заголовка `X-Telegram-Bot-Api-Secret-Token`    |
| `DATABASE_URL`   | SQLite / PostgreSQL строка подключения                    |
| `VERSION`        | Текущая версия приложения                                 |
| `ADMIN_TOKEN`    | Токен для админ-эндпоинтов `/api/v1/admin/*`              |
| `OPENAI_API_KEY` | Ключ OpenAI (при пустом значении роутер переключается в offline/local) |
| `OPENAI_MODEL_PRIMARY` | Имя модели для mini-ответов                         |
| `OPENAI_MODEL_DEEP`    | Имя модели для глубоких ответов                     |
| `OPENAI_DAILY_LIMIT_USD` / `OPENAI_SOFT_LIMIT_USD` | Жёсткий/мягкий лимит на расходы в сутки |
| `AI_ROUTER_MODE` | Ручной режим (`auto`, `mini_only`, `local_only`, `turbo_only`) |
| `AI_CACHE_TTL_SEC` | TTL кэша ответов в секундах                             |

## Логи запуска

В логе старта присутствует строка

```
✅ SoznAi запущен версия=6.0.0 mode=offline reason=telegram disabled
```

Она подтверждает успешную инициализацию, режим и причину.

## Дорожная карта v6.1

- Дополнительные визуализации аналитики (линейные/столбчатые чарты в UI, экспорт PDF).
- Расширенный AI-режим с обучением на пользовательских шаблонах и локальным fallback-моделям.
- E2E-тесты фронтенда (Playwright) и автоматическая публикация статики в CDN.

## Лицензия

MIT
