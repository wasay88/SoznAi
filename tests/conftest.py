from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

try:
    from backend.db import create_engine, create_session_factory, init_db
except ModuleNotFoundError:  # pragma: no cover - optional test dependency
    create_engine = create_session_factory = init_db = None


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def test_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    if create_engine is None or init_db is None:
        pytest.skip("database test dependencies not installed")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEBAPP_URL", raising=False)
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VERSION", "0.1.0-test")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("AI_ROUTER_MODE", "local_only")

    db_path = Path("data") / f"test_{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    from backend.app.main import app

    with TestClient(app) as client:
        client.headers.update({"X-Soznai-Tg-Id": "123456"})
        yield client


@pytest.fixture()
def temp_session_factory(tmp_path: Path):
    if create_engine is None or init_db is None:
        pytest.skip("database test dependencies not installed")
    db_path = tmp_path / f"unit_{uuid4().hex}.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    asyncio.run(init_db(engine, session_factory, "test", database_url))
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())
