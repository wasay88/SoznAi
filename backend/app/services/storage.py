from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from secrets import token_urlsafe
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..db.models import (
    AILimitChange,
    AIModeSwitch,
    AIUsageStat,
    EmotionEntry,
    InsightEntry,
    JournalEntry,
    PromptCacheEntry,
    SessionToken,
    SettingEntry,
    User,
    WeeklyInsight,
)

AI_MODE_KEY = "ai_router_mode"
AI_SOFT_LIMIT_KEY = "ai_soft_limit"
AI_HARD_LIMIT_KEY = "ai_hard_limit"
AI_BATCH_ENABLED_KEY = "ai_batch_enabled"


class StorageService:
    """Persist users, journal and emotion data."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def healthcheck(self) -> None:
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))

    # -- settings helpers ------------------------------------------------
    async def get_setting(self, key: str) -> str | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SettingEntry).where(SettingEntry.key == key)
            )
            entry = result.scalar_one_or_none()
            return entry.value if entry else None

    async def set_setting(self, key: str, value: str) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SettingEntry).where(SettingEntry.key == key)
            )
            entry = result.scalar_one_or_none()
            if entry is None:
                entry = SettingEntry(key=key, value=value)
                session.add(entry)
            else:
                entry.value = value
            await session.commit()

    async def ensure_ai_config(
        self,
        *,
        default_mode: str,
        soft_limit: float,
        hard_limit: float,
    ) -> dict[str, Any]:
        stored_mode = await self.get_setting(AI_MODE_KEY)
        stored_soft = await self.get_setting(AI_SOFT_LIMIT_KEY)
        stored_hard = await self.get_setting(AI_HARD_LIMIT_KEY)

        mode = stored_mode or default_mode
        try:
            soft_value = float(stored_soft) if stored_soft is not None else soft_limit
        except (TypeError, ValueError):
            soft_value = soft_limit
        try:
            hard_value = float(stored_hard) if stored_hard is not None else hard_limit
        except (TypeError, ValueError):
            hard_value = hard_limit

        # Ensure ordering of limits
        if hard_value < soft_value:
            hard_value = max(soft_value, hard_limit)

        await self.set_setting(AI_MODE_KEY, mode)
        await self.set_setting(AI_SOFT_LIMIT_KEY, f"{soft_value:.2f}")
        await self.set_setting(AI_HARD_LIMIT_KEY, f"{hard_value:.2f}")

        # Ensure audit trail exists at least once
        async with self._session_factory() as session:
            existing_mode = await session.scalar(
                select(AIModeSwitch).order_by(AIModeSwitch.id.desc())
            )
            if existing_mode is None:
                session.add(AIModeSwitch(mode=mode, actor="bootstrap"))
            existing_limit = await session.scalar(
                select(AILimitChange).order_by(AILimitChange.id.desc())
            )
            if existing_limit is None:
                session.add(
                    AILimitChange(
                        soft_limit=soft_value,
                        hard_limit=hard_value,
                        actor="bootstrap",
                    )
                )
            await session.commit()

        return {
            "mode": mode,
            "soft_limit": soft_value,
            "hard_limit": hard_value,
        }

    async def update_ai_limits(
        self, soft_limit: float, hard_limit: float, *, actor: str = "admin"
    ) -> dict[str, Any]:
        soft_value = max(0.0, float(soft_limit))
        hard_value = max(soft_value, float(hard_limit))
        await self.set_setting(AI_SOFT_LIMIT_KEY, f"{soft_value:.2f}")
        await self.set_setting(AI_HARD_LIMIT_KEY, f"{hard_value:.2f}")
        async with self._session_factory() as session:
            session.add(
                AILimitChange(
                    soft_limit=soft_value,
                    hard_limit=hard_value,
                    actor=actor,
                )
            )
            await session.commit()
        return {"soft_limit": soft_value, "hard_limit": hard_value}

    async def update_ai_mode(self, mode: str, *, actor: str = "admin") -> str:
        await self.set_setting(AI_MODE_KEY, mode)
        async with self._session_factory() as session:
            session.add(AIModeSwitch(mode=mode, actor=actor))
            await session.commit()
        return mode

    async def get_ai_limits(self) -> dict[str, float]:
        soft = await self.get_setting(AI_SOFT_LIMIT_KEY)
        hard = await self.get_setting(AI_HARD_LIMIT_KEY)
        try:
            soft_value = float(soft) if soft is not None else 0.0
        except (TypeError, ValueError):  # pragma: no cover - defensive
            soft_value = 0.0
        try:
            hard_value = float(hard) if hard is not None else soft_value
        except (TypeError, ValueError):  # pragma: no cover - defensive
            hard_value = soft_value
        if hard_value < soft_value:
            hard_value = soft_value
        return {
            "soft_limit": soft_value,
            "hard_limit": hard_value,
        }

    async def get_latest_mode(self) -> str | None:
        async with self._session_factory() as session:
            entry = await session.scalar(
                select(AIModeSwitch.mode).order_by(AIModeSwitch.created_at.desc())
            )
            return entry

    async def get_latest_limit_change(self) -> AILimitChange | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(AILimitChange).order_by(AILimitChange.created_at.desc())
            )

    async def set_batch_enabled(self, enabled: bool) -> bool:
        await self.set_setting(AI_BATCH_ENABLED_KEY, "1" if enabled else "0")
        return enabled

    async def is_batch_enabled(self) -> bool:
        value = await self.get_setting(AI_BATCH_ENABLED_KEY)
        return value == "1"

    # -- user management -------------------------------------------------
    async def ensure_user_by_telegram(self, tg_id: int) -> User:
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.tg_id == tg_id))
            if user:
                return user
            user = User(tg_id=tg_id)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_user_by_id(self, user_id: int) -> User | None:
        async with self._session_factory() as session:
            return await session.get(User, user_id)

    async def get_user_by_session(self, token: str) -> User | None:
        async with self._session_factory() as session:
            query = (
                select(User)
                .join(SessionToken)
                .where(SessionToken.token == token)
                .where(SessionToken.expires_at > datetime.utcnow())
            )
            return await session.scalar(query)

    async def issue_magic_link(self, user_id: int, email: str, ttl_hours: int = 24) -> SessionToken:
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        token_value = token_urlsafe(32)
        async with self._session_factory() as session:
            session_token = SessionToken(
                user_id=user_id,
                token=token_value,
                email=email,
                expires_at=expires_at,
            )
            session.add(session_token)
            await session.commit()
            await session.refresh(session_token)
            return session_token

    async def verify_magic_link(self, token: str) -> tuple[User, SessionToken] | None:
        async with self._session_factory() as session:
            query = (
                select(SessionToken)
                .where(SessionToken.token == token)
                .where(SessionToken.expires_at > datetime.utcnow())
            )
            session_token = await session.scalar(query)
            if not session_token:
                return None
            user = await session.get(User, session_token.user_id)
            if user is None:
                return None
            if session_token.email:
                user.email = session_token.email
            new_session = SessionToken(
                user_id=user.id,
                token=token_urlsafe(32),
                email=None,
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
            session.add(new_session)
            await session.delete(session_token)
            await session.commit()
            await session.refresh(new_session)
            return user, new_session

    # -- journal and emotion operations ----------------------------------
    async def add_journal_entry(
        self,
        *,
        user_id: int,
        text: str,
        source: str,
    ) -> JournalEntry:
        async with self._session_factory() as session:
            entry = JournalEntry(user_id=user_id, entry_text=text, source=source)
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def list_journal_entries(
        self,
        *,
        user_id: int,
        limit: int = 20,
    ) -> Sequence[JournalEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(JournalEntry)
                .where(JournalEntry.user_id == user_id)
                .order_by(JournalEntry.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def add_emotion_entry(
        self,
        *,
        user_id: int,
        emotion_code: str,
        intensity: int,
        note: str | None,
        source: str,
    ) -> EmotionEntry:
        async with self._session_factory() as session:
            entry = EmotionEntry(
                user_id=user_id,
                emotion_code=emotion_code,
                intensity=intensity,
                note=note,
                source=source,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def list_emotion_entries(
        self,
        *,
        user_id: int,
        limit: int = 20,
    ) -> Sequence[EmotionEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EmotionEntry)
                .where(EmotionEntry.user_id == user_id)
                .order_by(EmotionEntry.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    # -- analytics -------------------------------------------------------
    async def analytics_summary(self, user_id: int, days: int) -> dict[str, object]:
        since = datetime.utcnow() - timedelta(days=days)
        async with self._session_factory() as session:
            emotion_result = await session.execute(
                select(EmotionEntry).where(
                    EmotionEntry.user_id == user_id,
                    EmotionEntry.created_at >= since,
                )
            )
            journal_result = await session.execute(
                select(JournalEntry).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.created_at >= since,
                )
            )
            emotions = list(emotion_result.scalars().all())
            journals = list(journal_result.scalars().all())

        entries_count = len(emotions) + len(journals)
        mood_avg = 0.0
        if emotions:
            mood_avg = sum(e.intensity for e in emotions) / len(emotions)
        top_counter = Counter(e.emotion_code for e in emotions)
        top_emotions = [
            {"code": code, "count": count}
            for code, count in top_counter.most_common(3)
        ]
        last_entry_ts = None
        all_dates: set[datetime] = set()
        for entry in emotions + journals:
            all_dates.add(entry.created_at.replace(hour=0, minute=0, second=0, microsecond=0))
            if not last_entry_ts or entry.created_at > last_entry_ts:
                last_entry_ts = entry.created_at

        streak = 0
        if all_dates:
            current = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            while current in all_dates:
                streak += 1
                current -= timedelta(days=1)

        return {
            "streak_days": streak,
            "entries_count": entries_count,
            "mood_avg": round(mood_avg, 2) if emotions else None,
            "top_emotions": top_emotions,
            "last_entry_ts": last_entry_ts.isoformat() if last_entry_ts else None,
        }

    # -- AI usage, cache and insights -------------------------------------
    async def record_usage(
        self,
        *,
        user_id: int | None,
        model: str,
        kind: str,
        source: str,
        tokens_in: int,
        tokens_out: int,
        usd_cost: float,
    ) -> None:
        async with self._session_factory() as session:
            entry = AIUsageStat(
                user_id=user_id,
                model=model,
                kind=kind,
                source=source,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                usd_cost=usd_cost,
            )
            session.add(entry)
            await session.commit()

    async def usage_total_since(self, since: datetime) -> float:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.sum(AIUsageStat.usd_cost)).where(AIUsageStat.ts >= since)
            )
            value = result.scalar_one_or_none()
            return float(value or 0.0)

    async def usage_totals(self, days: int = 7) -> list[dict[str, Any]]:
        since = datetime.utcnow() - timedelta(days=days)
        async with self._session_factory() as session:
            result = await session.execute(
                select(AIUsageStat).where(AIUsageStat.ts >= since)
            )
            rows = list(result.scalars().all())

        aggregates: dict[tuple[date, str], dict[str, Any]] = {}
        for row in rows:
            day_key = row.ts.date()
            key = (day_key, row.model)
            bucket = aggregates.setdefault(
                key,
                {
                    "day": day_key.isoformat(),
                    "model": row.model,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "usd_cost": 0.0,
                    "requests": 0,
                },
            )
            bucket["tokens_in"] += row.tokens_in
            bucket["tokens_out"] += row.tokens_out
            bucket["usd_cost"] += float(row.usd_cost)
            bucket["requests"] += 1

        return sorted(aggregates.values(), key=lambda item: (item["day"], item["model"]))

    async def usage_overview(self, days: int = 7) -> dict[str, Any]:
        since = datetime.utcnow() - timedelta(days=days)
        async with self._session_factory() as session:
            result = await session.execute(
                select(AIUsageStat).where(AIUsageStat.ts >= since)
            )
            rows = list(result.scalars().all())

        total_requests = len(rows)
        tokens_in = sum(row.tokens_in for row in rows)
        tokens_out = sum(row.tokens_out for row in rows)
        total_cost = float(sum(row.usd_cost for row in rows))
        cache_hits = sum(1 for row in rows if row.source == "cache")
        model_totals: dict[str, int] = {}
        kind_totals: dict[str, int] = {}
        for row in rows:
            model_totals[row.model] = model_totals.get(row.model, 0) + 1
            kind_totals[row.kind] = kind_totals.get(row.kind, 0) + 1

        cache_rate = (cache_hits / total_requests) if total_requests else 0.0

        return {
            "requests": total_requests,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "usd_cost": total_cost,
            "cache_hits": cache_hits,
            "cache_rate": cache_rate,
            "requests_by_kind": kind_totals,
            "requests_by_model": model_totals,
        }

    async def usage_history(self, limit: int = 50) -> list[AIUsageStat]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AIUsageStat)
                .order_by(AIUsageStat.ts.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def cache_overview(self, days: int = 7) -> dict[str, Any]:
        since = datetime.utcnow() - timedelta(days=days)
        async with self._session_factory() as session:
            total_requests = await session.scalar(
                select(func.count(AIUsageStat.id)).where(AIUsageStat.ts >= since)
            )
            cache_hits = await session.scalar(
                select(func.count(AIUsageStat.id)).where(
                    AIUsageStat.ts >= since,
                    AIUsageStat.source == "cache",
                )
            )
            key_rows = await session.execute(
                select(
                    PromptCacheEntry.cache_key,
                    PromptCacheEntry.kind,
                    PromptCacheEntry.locale,
                    PromptCacheEntry.model,
                    PromptCacheEntry.expires_at,
                )
                .order_by(PromptCacheEntry.expires_at.desc())
                .limit(50)
            )
            cache_entries = key_rows.all()

        hits = int(cache_hits or 0)
        total = int(total_requests or 0)
        misses = max(total - hits, 0)
        hit_rate = hits / total if total else 0.0
        keys = [
            {
                "key": row.cache_key,
                "kind": row.kind,
                "locale": row.locale,
                "model": row.model,
                "expires_at": row.expires_at,
            }
            for row in cache_entries
        ]
        return {"hits": hits, "misses": misses, "hit_rate": hit_rate, "keys": keys}

    async def get_cache_entry(self, cache_key: str) -> PromptCacheEntry | None:
        now = datetime.utcnow()
        async with self._session_factory() as session:
            entry = await session.scalar(
                select(PromptCacheEntry).where(PromptCacheEntry.cache_key == cache_key)
            )
            if not entry:
                return None
            if entry.expires_at <= now:
                await session.delete(entry)
                await session.commit()
                return None
            return entry

    async def upsert_cache_entry(
        self,
        *,
        cache_key: str,
        kind: str,
        locale: str,
        prompt: str,
        response_text: str,
        model: str,
        source: str,
        tokens_in: int,
        tokens_out: int,
        usd_cost: float,
        ttl_seconds: int,
    ) -> None:
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        async with self._session_factory() as session:
            entry = await session.scalar(
                select(PromptCacheEntry).where(PromptCacheEntry.cache_key == cache_key)
            )
            if entry:
                entry.response_text = response_text
                entry.model = model
                entry.source = source
                entry.tokens_in = tokens_in
                entry.tokens_out = tokens_out
                entry.usd_cost = usd_cost
                entry.expires_at = expires_at
                entry.prompt = prompt
                entry.locale = locale
                entry.kind = kind
            else:
                entry = PromptCacheEntry(
                    cache_key=cache_key,
                    kind=kind,
                    locale=locale,
                    prompt=prompt,
                    response_text=response_text,
                    model=model,
                    source=source,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    usd_cost=usd_cost,
                    expires_at=expires_at,
                )
                session.add(entry)
            await session.commit()

    async def purge_expired_cache(self, limit: int = 100) -> int:
        now = datetime.utcnow()
        async with self._session_factory() as session:
            result = await session.execute(
                select(PromptCacheEntry.id).where(PromptCacheEntry.expires_at <= now).limit(limit)
            )
            ids = [row[0] for row in result.all()]
            if not ids:
                return 0
            await session.execute(delete(PromptCacheEntry).where(PromptCacheEntry.id.in_(ids)))
            await session.commit()
            return len(ids)

    async def list_recent_users(self, since: datetime) -> Sequence[int]:
        async with self._session_factory() as session:
            emotion_rows = await session.execute(
                select(EmotionEntry.user_id).where(EmotionEntry.created_at >= since)
            )
            journal_rows = await session.execute(
                select(JournalEntry.user_id).where(JournalEntry.created_at >= since)
            )
            emotion_ids = {uid for (uid,) in emotion_rows.all() if uid is not None}
            journal_ids = {uid for (uid,) in journal_rows.all() if uid is not None}
        return list(emotion_ids | journal_ids)

    async def fetch_recent_activity(
        self, user_id: int, since: datetime
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            emotion_rows = await session.execute(
                select(EmotionEntry).where(
                    EmotionEntry.user_id == user_id,
                    EmotionEntry.created_at >= since,
                )
            )
            journal_rows = await session.execute(
                select(JournalEntry).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.created_at >= since,
                )
            )
            emotions = list(emotion_rows.scalars().all())
            journals = list(journal_rows.scalars().all())
        return {
            "emotions": emotions,
            "journals": journals,
        }

    async def fetch_activity_range(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            emotion_rows = await session.execute(
                select(EmotionEntry)
                .where(EmotionEntry.user_id == user_id)
                .where(EmotionEntry.created_at >= start)
                .where(EmotionEntry.created_at < end)
                .order_by(EmotionEntry.created_at.asc())
            )
            journal_rows = await session.execute(
                select(JournalEntry)
                .where(JournalEntry.user_id == user_id)
                .where(JournalEntry.created_at >= start)
                .where(JournalEntry.created_at < end)
                .order_by(JournalEntry.created_at.asc())
            )
            return {
                "emotions": list(emotion_rows.scalars().all()),
                "journals": list(journal_rows.scalars().all()),
            }

    async def save_insight(self, user_id: int, day_value: date, text: str) -> None:
        async with self._session_factory() as session:
            entry = await session.scalar(
                select(InsightEntry).where(
                    InsightEntry.user_id == user_id,
                    InsightEntry.day == day_value,
                )
            )
            if entry:
                entry.text = text
                entry.created_at = datetime.utcnow()
            else:
                entry = InsightEntry(user_id=user_id, day=day_value, text=text)
                session.add(entry)
            await session.commit()

    async def list_insights(self, user_id: int, limit: int = 7) -> Sequence[InsightEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(InsightEntry)
                .where(InsightEntry.user_id == user_id)
                .order_by(InsightEntry.day.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_weekly_insight(
        self, user_id: int, week_start: date
    ) -> WeeklyInsight | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(WeeklyInsight)
                .where(WeeklyInsight.user_id == user_id)
                .where(WeeklyInsight.week_start == week_start)
            )

    async def save_weekly_insight(
        self,
        *,
        user_id: int,
        week_start: date,
        week_end: date,
        mood_avg: float | None,
        mood_volatility: float | None,
        top_emotions: list[dict[str, object]],
        journal_wordcloud: list[dict[str, object]],
        days_with_entries: int,
        longest_streak: int,
        entries_count: int,
        entries_by_day: list[dict[str, object]],
        summary: str | None,
        summary_model: str | None,
        summary_source: str | None,
        computed_at: datetime,
    ) -> WeeklyInsight:
        payload = {
            "mood_avg": mood_avg,
            "mood_volatility": mood_volatility,
            "top_emotions": json.dumps(top_emotions, ensure_ascii=False),
            "journal_wordcloud": json.dumps(journal_wordcloud, ensure_ascii=False),
            "days_with_entries": days_with_entries,
            "longest_streak": longest_streak,
            "entries_count": entries_count,
            "entries_by_day": json.dumps(entries_by_day, ensure_ascii=False),
            "summary": summary,
            "summary_model": summary_model,
            "summary_source": summary_source,
            "computed_at": computed_at,
        }
        async with self._session_factory() as session:
            entry = await session.scalar(
                select(WeeklyInsight)
                .where(WeeklyInsight.user_id == user_id)
                .where(WeeklyInsight.week_start == week_start)
            )
            if entry is None:
                entry = WeeklyInsight(
                    user_id=user_id,
                    week_start=week_start,
                    week_end=week_end,
                    **payload,
                )
                session.add(entry)
            else:
                entry.week_end = week_end
                for key, value in payload.items():
                    setattr(entry, key, value)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def list_weekly_insights(
        self,
        user_id: int,
        limit: int = 4,
    ) -> Sequence[WeeklyInsight]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(WeeklyInsight)
                .where(WeeklyInsight.user_id == user_id)
                .order_by(WeeklyInsight.week_start.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def export_user_data(self, user_id: int, days: int = 30) -> bytes:
        since = datetime.utcnow() - timedelta(days=days)
        async with self._session_factory() as session:
            emotions = await session.execute(
                select(EmotionEntry)
                .where(EmotionEntry.user_id == user_id, EmotionEntry.created_at >= since)
                .order_by(EmotionEntry.created_at.desc())
            )
            journals = await session.execute(
                select(JournalEntry)
                .where(JournalEntry.user_id == user_id, JournalEntry.created_at >= since)
                .order_by(JournalEntry.created_at.desc())
            )
            emotion_rows = list(emotions.scalars().all())
            journal_rows = list(journals.scalars().all())

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "type",
                "created_at",
                "emotion_code",
                "intensity",
                "note",
                "text",
                "source",
            ]
        )
        for entry in emotion_rows:
            writer.writerow(
                [
                    "emotion",
                    entry.created_at.isoformat(),
                    entry.emotion_code,
                    entry.intensity,
                    entry.note or "",
                    "",
                    entry.source,
                ]
            )
        for entry in journal_rows:
            writer.writerow(
                [
                    "journal",
                    entry.created_at.isoformat(),
                    "",
                    "",
                    "",
                    entry.entry_text,
                    entry.source,
                ]
            )
        return buffer.getvalue().encode("utf-8")

    async def delete_user(self, user_id: int) -> None:
        async with self._session_factory() as session:
            user = await session.get(User, user_id)
            if user:
                await session.delete(user)
                await session.commit()


__all__ = ["StorageService"]
