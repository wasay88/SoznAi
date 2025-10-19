from __future__ import annotations

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.app.core.security import resolve_authenticated_user


class _StubStorage:
    def __init__(self) -> None:
        self.last_tg_id: int | None = None

    async def ensure_user_by_telegram(self, tg_id: int):
        self.last_tg_id = tg_id
        return SimpleNamespace(id=1, tg_id=tg_id)

    async def get_user_by_session(self, token: str):
        if token == "valid":
            return SimpleNamespace(id=2, tg_id=987654)
        return None


def _app_with_security(storage: _StubStorage) -> FastAPI:
    app = FastAPI()
    app.state.storage_service = storage

    @app.get("/secure")
    async def secure_endpoint(user_id: int = Depends(resolve_authenticated_user)) -> dict[str, int]:
        return {"user": user_id}

    return app


def test_resolve_authenticated_user_header() -> None:
    storage = _StubStorage()
    app = _app_with_security(storage)
    with TestClient(app) as client:
        response = client.get("/secure", headers={"X-Soznai-Tg-Id": "456"})
        assert response.status_code == 200
        assert response.json()["user"] == 1
        assert storage.last_tg_id == 456


def test_resolve_authenticated_user_cookie() -> None:
    storage = _StubStorage()
    app = _app_with_security(storage)
    with TestClient(app) as client:
        client.cookies.set("soz_session", "valid")
        response = client.get("/secure")
        assert response.status_code == 200
        assert response.json()["user"] == 2


def test_resolve_authenticated_user_invalid_header() -> None:
    storage = _StubStorage()
    app = _app_with_security(storage)
    with TestClient(app) as client:
        response = client.get("/secure", headers={"X-Soznai-Tg-Id": "oops"})
        assert response.status_code == 400


def test_resolve_authenticated_user_missing() -> None:
    storage = _StubStorage()
    app = _app_with_security(storage)
    with TestClient(app) as client:
        response = client.get("/secure")
        assert response.status_code == 401
