from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.db.models import EmotionEntry, JournalEntry
from backend.app.insights import WeeklyInsightsEngine
from backend.app.services.storage import StorageService


@pytest.mark.anyio
async def test_weekly_insight_computation(temp_session_factory) -> None:
    storage = StorageService(temp_session_factory)
    settings = SimpleNamespace(insights_ai_enabled=False, insights_debounce_seconds=60)
    engine = WeeklyInsightsEngine(storage, settings=settings, ai_router=None, debounce_seconds=0)

    user = await storage.ensure_user_by_telegram(555)
    week_start = date(2024, 7, 1)
    base_dt = datetime(2024, 7, 1, 9, 0, 0)
    async with temp_session_factory() as session:
        session.add_all(
            [
                EmotionEntry(
                    user_id=user.id,
                    emotion_code="joy",
                    intensity=4,
                    created_at=base_dt,
                ),
                EmotionEntry(
                    user_id=user.id,
                    emotion_code="calm",
                    intensity=2,
                    created_at=base_dt + timedelta(days=1),
                ),
                EmotionEntry(
                    user_id=user.id,
                    emotion_code="joy",
                    intensity=5,
                    created_at=base_dt + timedelta(days=2),
                ),
            ]
        )
        session.add(
            JournalEntry(
                user_id=user.id,
                entry_text="Сегодня прогулка в саду наполнила теплом",
                created_at=base_dt + timedelta(days=2, hours=2),
            )
        )
        await session.commit()

    updated, debounced, empty = await engine.ensure_range(
        user.id,
        weeks=1,
        week_start=week_start,
        force=True,
        locale="ru",
    )
    assert updated == 1
    assert debounced == 0
    assert empty == 0

    rows = await storage.list_weekly_insights(user.id, limit=1)
    assert rows
    entry = rows[0]
    assert entry.week_start == week_start
    assert entry.week_end == week_start + timedelta(days=6)
    assert entry.entries_count == 4
    assert entry.days_with_entries == 3
    assert entry.longest_streak == 3
    assert pytest.approx(entry.mood_avg or 0, rel=1e-2) == 3.67
    assert entry.mood_volatility is not None

    top = json.loads(entry.top_emotions)
    assert top[0]["code"] == "joy"
    wordcloud = json.loads(entry.journal_wordcloud)
    words = {item["word"] for item in wordcloud}
    assert "прогулка" in words or "сад" in words
    day_counts = json.loads(entry.entries_by_day)
    assert len(day_counts) == 7
    monday = next(item for item in day_counts if item["day"] == 0)
    assert monday["count"] == 1
    wednesday = next(item for item in day_counts if item["day"] == 2)
    assert wednesday["count"] >= 2


@pytest.mark.anyio
async def test_weekly_insight_debounce(temp_session_factory) -> None:
    storage = StorageService(temp_session_factory)
    settings = SimpleNamespace(insights_ai_enabled=False, insights_debounce_seconds=300)
    engine = WeeklyInsightsEngine(storage, settings=settings, ai_router=None)

    user = await storage.ensure_user_by_telegram(777)
    await engine.ensure_range(user.id, weeks=1, force=True)

    updated, debounced, empty = await engine.ensure_range(user.id, weeks=1)
    assert updated == 0
    assert debounced == 1
    assert empty >= 0


@pytest.mark.anyio
async def test_weekly_insight_empty_user(temp_session_factory) -> None:
    storage = StorageService(temp_session_factory)
    settings = SimpleNamespace(insights_ai_enabled=False, insights_debounce_seconds=60)
    engine = WeeklyInsightsEngine(storage, settings=settings, ai_router=None)

    user = await storage.ensure_user_by_telegram(888)
    updated, debounced, empty = await engine.ensure_range(user.id, weeks=1, force=True)
    assert updated == 0
    assert debounced == 0
    assert empty == 1
    rows = await storage.list_weekly_insights(user.id)
    assert rows == []
