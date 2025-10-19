from __future__ import annotations

import pytest
from sqlalchemy import text

from backend.db import create_engine


@pytest.mark.anyio
async def test_create_engine_normalizes_postgres_url() -> None:
    engine = create_engine("postgres://user:pass@localhost:5432/example")
    try:
        assert str(engine.url).startswith("postgresql+asyncpg://")
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_create_engine_enables_sqlite_foreign_keys() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA foreign_keys"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()
