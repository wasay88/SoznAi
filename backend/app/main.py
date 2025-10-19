from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.db import create_engine, create_session_factory, init_db

from .ai import AIRouter, DailyLimiter, PromptCache, UsageTracker
from .ai.openai_client import OpenAIClient
from .api.v1.routes import router as v1_router
from .core.config import Settings, get_settings
from .core.logging import configure_logging
from .core.security import enforce_webhook_secret
from .middleware import RequestLoggingMiddleware
from .schemas.mode import ModeResponse
from .schemas.webhook import TelegramWebhookUpdate, WebhookResponse
from .services.modes import ModeManager
from .services.ratelimit import RateLimiter
from .services.storage import StorageService
from .services.telegram import TelegramService

logger = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"
ADMIN_DIR = FRONTEND_DIR / "admin"
ADMIN_INDEX = ADMIN_DIR / "index.html"


def get_mode_manager_from_app(request: Request) -> ModeManager:
    return request.app.state.mode_manager


def get_telegram_service_from_app(request: Request) -> TelegramService:
    return request.app.state.telegram_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure application services during startup and ensure graceful shutdown."""

    configure_logging()
    settings: Settings = get_settings()
    mode_manager = ModeManager()

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    await init_db(engine, session_factory, settings.version, settings.database_url)
    storage_service = StorageService(session_factory)
    rate_limiter = RateLimiter()
    ai_limiter = DailyLimiter(
        storage_service,
        settings.openai_soft_limit_usd,
        settings.openai_daily_limit_usd,
    )
    ai_usage_tracker = UsageTracker(storage_service, ai_limiter)
    prompt_cache = PromptCache(storage_service, settings.ai_cache_ttl_sec)
    openai_client = OpenAIClient(settings.openai_api_key)
    ai_router = AIRouter(
        settings=settings,
        storage=storage_service,
        cache=prompt_cache,
        usage_tracker=ai_usage_tracker,
        limiter=ai_limiter,
        openai_client=openai_client,
    )

    telegram_service = TelegramService(
        token=settings.bot_token,
        webhook_url=str(settings.webapp_url) if settings.webapp_url else None,
        timeout=settings.request_timeout_seconds,
        retries=settings.retry_attempts,
        secret_token=settings.webhook_secret_token,
        storage=storage_service,
        ai_router=ai_router,
    )

    app.state.settings = settings
    app.state.mode_manager = mode_manager
    app.state.telegram_service = telegram_service
    app.state.storage_service = storage_service
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    app.state.rate_limiter = rate_limiter
    app.state.ai_router = ai_router
    app.state.ai_usage_tracker = ai_usage_tracker
    app.state.ai_cache = prompt_cache
    app.state.ai_limiter = ai_limiter

    logger.info("Starting SoznAi %s", settings.version)

    await ai_router.initialize()

    if telegram_service.available:
        try:
            success = await telegram_service.ensure_webhook()
        except Exception as exc:
            logger.warning("Failed to configure telegram webhook: %s", exc, exc_info=True)
            status_obj = await mode_manager.set_degraded("telegram webhook error")
            logger.warning(
                "Application mode %s: %s",
                status_obj.state.value,
                status_obj.reason,
            )
        else:
            if success:
                status_obj = await mode_manager.set_online("telegram webhook active")
                logger.info(
                    "Application mode %s: %s",
                    status_obj.state.value,
                    status_obj.reason,
                )
            else:
                status_obj = await mode_manager.set_degraded(
                    "unable to configure telegram webhook"
                )
                logger.warning(
                    "Application mode %s: %s",
                    status_obj.state.value,
                    status_obj.reason,
                )
    else:
        status_obj = await mode_manager.set_offline("telegram disabled")
        logger.info(
            "Application mode %s: %s",
            status_obj.state.value,
            status_obj.reason,
        )

    snapshot = await mode_manager.get_status()
    logger.info(
        "✅ SoznAi запущен версия=%s mode=%s reason=%s",
        settings.version,
        snapshot.state.value,
        snapshot.reason,
    )

    try:
        yield
    finally:
        await telegram_service.close()
        await app.state.db_engine.dispose()


app = FastAPI(title="SoznAi", version=get_settings().version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR, html=False), name="static")
if ADMIN_DIR.exists():
    app.mount("/admin/static", StaticFiles(directory=ADMIN_DIR, html=False), name="admin-static")
else:  # pragma: no cover - defensive logging
    logger.warning("Frontend directory not found at %s", FRONTEND_DIR)

app.include_router(v1_router)


@app.get("/healthz")
async def healthz(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    mode_manager = get_mode_manager_from_app(request)
    status_obj = await mode_manager.get_status()
    return {
        "status": "ok",
        "mode": status_obj.state.value,
        "version": settings.version,
    }


@app.get("/readyz")
async def readyz(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    storage: StorageService = request.app.state.storage_service
    telegram_service = get_telegram_service_from_app(request)

    db_ok = True
    db_detail = "ok"
    try:
        await storage.healthcheck()
    except Exception as exc:  # pragma: no cover - defensive logging
        db_ok = False
        db_detail = str(exc)

    tg_ok: bool
    tg_detail: str
    if settings.bot_token:
        try:
            tg_ok, tg_detail = await telegram_service.check_readiness(request_timeout=2.0)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Telegram readiness check failed: %s", exc)
            tg_ok = False
            tg_detail = "unexpected"
    else:
        tg_ok = True
        tg_detail = "telegram disabled"

    ready = db_ok and tg_ok
    return {
        "ready": ready,
        "db": {"ok": db_ok, "detail": db_detail},
        "tg": {"ok": tg_ok, "detail": tg_detail},
    }


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8")
    return "<h1>SoznAi</h1><p>Помощник самоосознанности: дыхание, эмоции, дневник.</p>"


@app.get("/admin", response_class=HTMLResponse)
async def admin_index() -> str:
    if ADMIN_INDEX.exists():
        return ADMIN_INDEX.read_text(encoding="utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin ui missing")


@app.get("/mode", response_model=ModeResponse)
async def public_mode(request: Request) -> ModeResponse:
    mode_manager = get_mode_manager_from_app(request)
    status_obj = await mode_manager.get_status()
    return ModeResponse(
        mode=status_obj.state,
        online=status_obj.online,
        reason=status_obj.reason,
    )


@app.post("/webhook")
async def public_webhook(
    request: Request,
    update: TelegramWebhookUpdate,
    _: None = Depends(enforce_webhook_secret),
) -> WebhookResponse:
    mode_manager = get_mode_manager_from_app(request)
    telegram_service = get_telegram_service_from_app(request)
    if not telegram_service.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram unavailable",
        )
    return await telegram_service.process_update(update, mode_manager)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/auth/verify", response_class=HTMLResponse)
async def verify_magic_link(request: Request, token: str) -> HTMLResponse:
    storage: StorageService = request.app.state.storage_service
    result = await storage.verify_magic_link(token)
    if not result:
        return HTMLResponse("<h1>Verification failed</h1>", status_code=status.HTTP_400_BAD_REQUEST)

    _user, session_token = result
    content = "<h1>Verified</h1><p>Вы успешно подтвердили доступ.</p>"
    response = HTMLResponse(content)
    response.set_cookie(
        "soz_session",
        session_token.token,
        httponly=True,
        secure=False,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )
    return response
