from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.main import app
from backend.app.schemas.webhook import WebhookResponse
from backend.app.services.telegram import TelegramService


def test_health_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "offline"


def test_mode_endpoint_offline(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/mode")
    assert response.status_code == 200
    assert response.json()["mode"] == "offline"


def test_readyz_without_bot_token(test_client: TestClient) -> None:
    response = test_client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["db"]["ok"] is True
    assert body["tg"]["detail"] == "telegram disabled"


def test_metrics_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/metrics")
    assert response.status_code == 200
    assert "soznai_requests_total" in response.text


def test_auth_required_for_protected_routes() -> None:
    with TestClient(app) as anonymous_client:
        response = anonymous_client.post(
            "/api/v1/journal",
            json={"text": "entry"},
        )
        assert response.status_code == 401


def test_journal_crud_flow(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/api/v1/journal",
        json={"text": "Сегодня благодарен за прогулку", "source": "test"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["ok"] is True
    assert isinstance(created["id"], int)

    list_response = test_client.get("/api/v1/journal")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) >= 1
    assert items[0]["text"]


def test_emotion_crud_flow(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/api/v1/emotions",
        json={"emotion_code": "joy", "intensity": 4, "note": "солнечно"},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["ok"] is True
    assert isinstance(created["id"], int)

    list_response = test_client.get("/api/v1/emotions")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) >= 1
    assert items[0]["emotion_code"]


def test_analytics_summary_returns_aggregates(test_client: TestClient) -> None:
    test_client.post(
        "/api/v1/emotions",
        json={"emotion_code": "calm", "intensity": 3},
    )
    test_client.post(
        "/api/v1/journal",
        json={"text": "Сегодня всё спокойно"},
    )
    response = test_client.get("/api/v1/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert "streak_days" in data
    assert "entries_count" in data
    assert "top_emotions" in data


def test_weekly_insights_endpoint_returns_data(test_client: TestClient) -> None:
    test_client.post(
        "/api/v1/emotions",
        json={"emotion_code": "joy", "intensity": 4},
    )
    test_client.post(
        "/api/v1/journal",
        json={"text": "Сегодня был насыщенный день", "source": "test"},
    )
    response = test_client.get("/api/v1/insights/weekly?range=2")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    if payload["items"]:
        first = payload["items"][0]
        assert "week_start" in first
        assert "mood_avg" in first
        assert "entries_count" in first
        assert "entries_by_day" in first


def test_magic_link_flow_sets_cookie(test_client: TestClient) -> None:
    create = test_client.post(
        "/api/v1/auth/magiclink",
        json={"email": "user@example.com"},
    )
    assert create.status_code == 200
    token = create.json()["token"]
    verify = test_client.get(f"/auth/verify?token={token}")
    assert verify.status_code == 200
    assert verify.cookies.get("soz_session")


def test_export_endpoint_returns_csv(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/me/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "type" in response.text


def test_delete_me_wipes_data(test_client: TestClient) -> None:
    test_client.post("/api/v1/journal", json={"text": "Удалить"})
    delete_response = test_client.delete("/api/v1/me")
    assert delete_response.status_code == 204
    after = test_client.get("/api/v1/journal")
    assert after.status_code == 200
    assert after.json()["items"] == []


def test_weekly_insights_recompute_requires_admin(test_client: TestClient) -> None:
    forbidden = test_client.post("/api/v1/insights/recompute", json={})
    assert forbidden.status_code in (401, 403)

    allowed = test_client.post(
        "/api/v1/insights/recompute",
        json={"weeks": 1},
        headers={"X-Soznai-Admin-Token": "test-admin"},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert "users_processed" in body


def test_frontend_root_served(test_client: TestClient) -> None:
    response = test_client.get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html" in response.text


@pytest.mark.parametrize("path", ["/static/app.js", "/static/styles.css"])
def test_static_assets_available(test_client: TestClient, path: str) -> None:
    response = test_client.get(path)
    assert response.status_code == 200
    assert response.text


def test_webhook_requires_telegram_config(test_client: TestClient) -> None:
    payload = {"update_id": 1, "message": {"message_id": 1, "text": "hi"}}
    response = test_client.post("/api/v1/webhook", json=payload)
    assert response.status_code == 503


def test_public_mode_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/mode")
    assert response.status_code == 200
    assert response.json()["mode"] == "offline"


def test_update_mode_endpoint_changes_state(test_client: TestClient) -> None:
    payload = {"target_mode": "degraded", "reason": "maintenance"}
    response = test_client.post("/api/v1/mode", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "degraded"
    assert body["reason"] == "maintenance"


@pytest.mark.anyio
async def test_versioned_webhook_calls_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    monkeypatch.setenv("WEBHOOK_SECRET", "secret")
    get_settings.cache_clear()

    ensure_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(TelegramService, "ensure_webhook", ensure_mock)

    with TestClient(app) as client:
        service = client.app.state.telegram_service
        monkeypatch.setattr(
            service,
            "process_update",
            AsyncMock(return_value=WebhookResponse(response="ok", delivered=True)),
        )
        payload = {
            "update_id": 1,
            "message": {"message_id": 1, "text": "/start", "chat": {"id": 10}},
        }
        forbidden = client.post("/api/v1/webhook", json=payload)
        assert forbidden.status_code == 401

        allowed = client.post(
            "/api/v1/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["response"] == "ok"

    ensure_mock.assert_awaited_once()
    get_settings.cache_clear()
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)


def test_ai_ask_returns_local_response(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/v1/ai/ask",
        json={"kind": "quick_tip", "text": "что делать?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] in {"local", "template"}
    assert isinstance(data["text"], str)


def test_ai_limits_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/ai/limits")
    assert response.status_code == 200
    body = response.json()
    assert "mode" in body
    assert "today_spend" in body


def test_admin_endpoints_require_token(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/admin/ai/stats")
    assert response.status_code == 401 or response.status_code == 503


def test_admin_run_daily_with_token(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/v1/admin/run/daily",
        headers={"Authorization": "Bearer test-admin"},
    )
    assert response.status_code == 200
    assert "created" in response.json()


def test_admin_stats_and_history(test_client: TestClient) -> None:
    stats = test_client.get(
        "/api/v1/admin/ai/stats",
        headers={"Authorization": "Bearer test-admin"},
    )
    assert stats.status_code == 200
    body = stats.json()
    assert body["overview"]["mode"]
    assert "cost_per_day" in body

    history = test_client.get(
        "/api/v1/admin/ai/history",
        headers={"Authorization": "Bearer test-admin"},
    )
    assert history.status_code == 200
    history_body = history.json()
    assert "items" in history_body


def test_admin_limits_and_batch_controls(test_client: TestClient) -> None:
    limits = test_client.post(
        "/api/v1/admin/ai/limits",
        headers={"Authorization": "Bearer test-admin"},
        json={"soft": 0.02, "hard": 0.05},
    )
    assert limits.status_code == 200
    payload = limits.json()
    assert payload["soft"] == pytest.approx(0.02, rel=1e-3)

    batch_toggle = test_client.post(
        "/api/v1/admin/ai/batch",
        headers={"Authorization": "Bearer test-admin"},
        json={"enabled": True},
    )
    assert batch_toggle.status_code == 200
    assert batch_toggle.json()["enabled"] is True


@pytest.mark.anyio
async def test_public_webhook_calls_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    monkeypatch.setenv("WEBHOOK_SECRET", "secret")
    get_settings.cache_clear()

    ensure_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(TelegramService, "ensure_webhook", ensure_mock)

    with TestClient(app) as client:
        service = client.app.state.telegram_service
        monkeypatch.setattr(
            service,
            "process_update",
            AsyncMock(return_value=WebhookResponse(response="ok", delivered=True)),
        )
        payload = {
            "update_id": 2,
            "message": {"message_id": 2, "text": "/start", "chat": {"id": 99}},
        }
        allowed = client.post(
            "/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["delivered"] is True

    ensure_mock.assert_awaited_once()
    get_settings.cache_clear()
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEBAPP_URL", raising=False)


@pytest.mark.anyio
async def test_lifespan_sets_online_when_webhook_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    get_settings.cache_clear()
    ensure_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(TelegramService, "ensure_webhook", ensure_mock)

    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.json()["mode"] == "online"

    ensure_mock.assert_awaited_once()
    get_settings.cache_clear()
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEBAPP_URL", raising=False)


@pytest.mark.anyio
async def test_lifespan_marks_degraded_when_webhook_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    get_settings.cache_clear()
    ensure_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(TelegramService, "ensure_webhook", ensure_mock)

    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.json()["mode"] == "degraded"

    ensure_mock.assert_awaited_once()
    get_settings.cache_clear()
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEBAPP_URL", raising=False)


@pytest.mark.anyio
async def test_lifespan_handles_webhook_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    get_settings.cache_clear()
    ensure_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(TelegramService, "ensure_webhook", ensure_mock)

    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.json()["mode"] == "degraded"
        status = client.app.state.mode_manager.snapshot()
        assert status.reason == "telegram webhook error"
    ensure_mock.assert_awaited_once()
    get_settings.cache_clear()
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEBAPP_URL", raising=False)
