from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.app.db import EmotionEntry, JournalEntry, SettingEntry, User


@pytest.mark.anyio
async def test_journal_and_emotion_crud(temp_session_factory):
    session_factory = temp_session_factory

    async with session_factory() as session:
        user = User(tg_id=999)
        session.add(user)
        await session.flush()
        journal = JournalEntry(user_id=user.id, entry_text="note", source="unit-test")
        emotion = EmotionEntry(
            user_id=user.id,
            emotion_code="joy",
            intensity=5,
            note="sunny",
            source="unit-test",
        )
        session.add_all([journal, emotion])
        await session.commit()

        await session.refresh(journal)
        await session.refresh(emotion)

        assert journal.id > 0
        assert emotion.id > 0

    async with session_factory() as session:
        journals = (await session.execute(select(JournalEntry))).scalars().all()
        emotions = (await session.execute(select(EmotionEntry))).scalars().all()
        assert any(item.entry_text == "note" for item in journals)
        assert any(item.emotion_code == "joy" for item in emotions)


@pytest.mark.anyio
async def test_setting_entry_unique_key(temp_session_factory):
    session_factory = temp_session_factory

    async with session_factory() as session:
        session.add(SettingEntry(key="theme", value="light"))
        await session.commit()

    async with session_factory() as session:
        query = select(SettingEntry).where(SettingEntry.key == "theme")
        result = await session.execute(query)
        setting = result.scalar_one()
        setting.value = "dark"
        await session.commit()

    async with session_factory() as session:
        query = select(SettingEntry).where(SettingEntry.key == "theme")
        setting = (await session.execute(query)).scalar_one()
        assert setting.value == "dark"
