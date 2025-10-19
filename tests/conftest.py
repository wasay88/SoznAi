from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from backend.db import create_engine, create_session_factory, init_db


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def test_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
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


@pytest_asyncio.fixture()
async def temp_session_factory(tmp_path: Path):
    db_path = tmp_path / f"unit_{uuid4().hex}.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_db(engine, session_factory, "test", database_url)
    try:
        yield session_factory
    finally:
        await engine.dispose()
