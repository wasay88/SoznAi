from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.db.models import Base, SettingEntry


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    try:
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(
            dbapi_connection,
            connection_record,
        ) -> None:  # pragma: no cover - event hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    except ImportError:  # pragma: no cover - defensive
        return

DEFAULT_SQLITE_URL = "sqlite:///./data/soznai.db"


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _ensure_sqlite_path(url: str) -> None:
    if "///" not in url:
        return
    path_part = url.split("///", maxsplit=1)[-1]
    if path_part in {"", ":memory:"}:
        return
    Path(path_part).parent.mkdir(parents=True, exist_ok=True)


def _normalize_database_url(raw_url: str | None) -> str:
    if not raw_url:
        raw_url = DEFAULT_SQLITE_URL

    url = str(raw_url)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)

    if url.startswith("sqlite+aiosqlite:///"):
        _ensure_sqlite_path(url)

    return url


def create_engine(database_url: str | None) -> AsyncEngine:
    normalized = _normalize_database_url(database_url)
    engine = create_async_engine(normalized, future=True, echo=False)
    if normalized.startswith("sqlite"):
        _enable_sqlite_foreign_keys(engine)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _make_alembic_config(database_url: str) -> Config:
    root = _project_root()
    cfg = Config(str(root.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _run_migrations(database_url: str) -> None:
    config = _make_alembic_config(database_url)
    command.upgrade(config, "head")


async def _apply_migrations(database_url: str | None) -> None:
    if not database_url:
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_migrations, database_url)


async def init_db(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    version: str,
    database_url: str | None = None,
) -> None:
    normalized_url = _normalize_database_url(database_url) if database_url else None
    await _apply_migrations(normalized_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        result = await session.execute(
            select(SettingEntry).where(SettingEntry.key == "schema_version")
        )
        setting = result.scalar_one_or_none()
        if setting is None:
            session.add(SettingEntry(key="schema_version", value=version))
        else:
            setting.value = version
        await session.commit()


__all__ = [
    "create_engine",
    "create_session_factory",
    "init_db",
]
