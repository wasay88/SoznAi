from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from backend.app.services.storage import StorageService
from backend.db import create_engine, create_session_factory, init_db


@pytest.mark.anyio
async def test_storage_service_crud(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_db(engine, session_factory, "test", database_url)

    storage = StorageService(session_factory)
    user = await storage.ensure_user_by_telegram(42)

    saved_journal = await storage.add_journal_entry(user_id=user.id, text="заметка", source="test")
    saved_emotion = await storage.add_emotion_entry(
        user_id=user.id,
        emotion_code="joy",
        intensity=4,
        note="солнце",
        source="test",
    )

    journals = await storage.list_journal_entries(user_id=user.id)
    emotions = await storage.list_emotion_entries(user_id=user.id)

    assert saved_journal.id > 0
    assert saved_emotion.id > 0
    assert journals[0].entry_text == "заметка"
    assert emotions[0].emotion_code == "joy"

    summary = await storage.analytics_summary(user.id, days=7)
    assert summary["entries_count"] == 2

    await engine.dispose()


@pytest.mark.anyio
async def test_magic_link_and_export(tmp_path: Path) -> None:
    db_path = tmp_path / "magic.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_db(engine, session_factory, "test", database_url)

    storage = StorageService(session_factory)
    user = await storage.ensure_user_by_telegram(111)

    token = await storage.issue_magic_link(user_id=user.id, email="user@example.com")
    verified = await storage.verify_magic_link(token.token)
    assert verified is not None
    verified_user, session_token = verified
    assert verified_user.email == "user@example.com"
    assert session_token.token

    await storage.add_emotion_entry(
        user_id=user.id,
        emotion_code="calm",
        intensity=2,
        note=None,
        source="test",
    )
    csv_bytes = await storage.export_user_data(user_id=user.id)
    assert b"emotion" in csv_bytes

    await storage.delete_user(user.id)
    empty = await storage.list_journal_entries(user_id=user.id)
    assert empty == []

    await engine.dispose()


@pytest.mark.anyio
async def test_ai_usage_and_cache(tmp_path: Path) -> None:
    db_path = tmp_path / "ai.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_db(engine, session_factory, "test", database_url)

    storage = StorageService(session_factory)
    config = await storage.ensure_ai_config(default_mode="auto", soft_limit=0.5, hard_limit=1.0)
    assert config["mode"] == "auto"

    await storage.record_usage(
        user_id=None,
        model="gpt-mini",
        kind="quick_tip",
        source="mini",
        tokens_in=10,
        tokens_out=20,
        usd_cost=0.01,
    )
    total = await storage.usage_total_since(datetime.utcnow() - timedelta(days=1))
    assert total >= 0.01

    overview = await storage.usage_overview(days=7)
    assert overview["requests"] >= 1
    assert overview["cache_rate"] >= 0.0

    await storage.set_batch_enabled(True)
    assert await storage.is_batch_enabled() is True

    await storage.upsert_cache_entry(
        cache_key="abc",
        kind="quick_tip",
        locale="ru",
        prompt="Привет",
        response_text="Очень длинный ответ " * 4,
        model="gpt-mini",
        source="mini",
        tokens_in=10,
        tokens_out=20,
        usd_cost=0.01,
        ttl_seconds=3600,
    )
    cache_entry = await storage.get_cache_entry("abc")
    assert cache_entry is not None
    assert cache_entry.model == "gpt-mini"

    await engine.dispose()


@pytest.mark.anyio
async def test_ai_config_helpers_and_insights(temp_session_factory) -> None:
    storage = StorageService(temp_session_factory)

    # corrupt stored values to trigger fallback and ordering logic
    await storage.set_setting("ai_soft_limit", "not-a-number")
    await storage.set_setting("ai_hard_limit", "1")
    await storage.set_setting("ai_router_mode", "mini_only")
    config = await storage.ensure_ai_config(default_mode="auto", soft_limit=0.2, hard_limit=0.5)
    assert config["mode"] == "mini_only"
    assert config["soft_limit"] == 0.2
    assert config["hard_limit"] >= config["soft_limit"]

    stored_limits = await storage.update_ai_limits(0.3, 0.1)
    assert stored_limits["hard_limit"] >= stored_limits["soft_limit"]

    await storage.update_ai_mode("turbo_only")

    # cache expiration and purge paths
    await storage.upsert_cache_entry(
        cache_key="expired",
        kind="quick_tip",
        locale="ru",
        prompt="пора отдохнуть",
        response_text="длинный ответ" * 20,
        model="template",
        source="template",
        tokens_in=0,
        tokens_out=0,
        usd_cost=0.0,
        ttl_seconds=-5,
    )
    assert await storage.get_cache_entry("expired") is None
    removed = await storage.purge_expired_cache()
    assert removed >= 0

    user = await storage.ensure_user_by_telegram(900)
    await storage.add_journal_entry(user_id=user.id, text="день 1", source="test")
    await storage.add_emotion_entry(
        user_id=user.id,
        emotion_code="calm",
        intensity=3,
        note=None,
        source="test",
    )

    since = datetime.utcnow() - timedelta(days=1)
    recent_users = await storage.list_recent_users(since)
    assert user.id in recent_users

    activity = await storage.fetch_recent_activity(user.id, since)
    assert activity["journals"] and activity["emotions"]

    day_value = date.today()
    await storage.save_insight(user.id, day_value, "initial")
    await storage.save_insight(user.id, day_value, "updated")
    insights = await storage.list_insights(user.id)
    assert insights[0].text == "updated"
