# ruff: noqa: RUF001

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime, timedelta
from itertools import pairwise

from ..core.config import Settings
from ..services.storage import StorageService

try:  # pragma: no cover - typing only
    from ..ai.router import AIResponse, AIRouter
except Exception:  # pragma: no cover - optional import guard for typing
    AIRouter = None  # type: ignore
    AIResponse = None  # type: ignore

_WORD_RE = re.compile(r"[\wёЁ]+", flags=re.UNICODE)
_STOPWORDS_RU = {
    "и",
    "в",
    "во",
    "на",
    "но",
    "что",
    "это",
    "как",
    "к",
    "из",
    "у",
    "с",
    "для",
    "а",
    "по",
    "мы",
    "я",
    "он",
    "она",
    "они",
    "ли",
    "не",
    "до",
    "от",
    "за",
    "то",
    "ну",
    "так",
}
_STOPWORDS_EN = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "is",
    "it",
    "at",
    "by",
    "be",
    "this",
    "that",
    "i",
    "we",
    "you",
    "they",
    "from",
    "as",
    "are",
}


class WeeklyInsightsEngine:
    """Compute and cache weekly aggregates over user activity."""

    def __init__(
        self,
        storage: StorageService,
        *,
        settings: Settings,
        ai_router: AIRouter | None = None,
        debounce_seconds: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._storage = storage
        self._settings = settings
        self._ai_router = ai_router if settings.insights_ai_enabled else None
        self._debounce_seconds = debounce_seconds or settings.insights_debounce_seconds
        self._clock = clock or datetime.utcnow
        self._recent_runs: dict[tuple[int, date], datetime] = {}

    async def ensure_range(
        self,
        user_id: int,
        *,
        weeks: int,
        week_start: date | None = None,
        force: bool = False,
        locale: str = "ru",
    ) -> tuple[int, int, int]:
        start = self._normalize_week_start(week_start or self._clock().date())
        updated = 0
        debounced = 0
        empty = 0
        for offset in range(weeks):
            current_week = start - timedelta(weeks=offset)
            result = await self._recompute_single(
                user_id=user_id,
                week_start=current_week,
                force=force,
                locale=locale,
            )
            if result == "updated":
                updated += 1
            elif result == "debounced":
                debounced += 1
            elif result == "empty":
                empty += 1
        return updated, debounced, empty

    async def recompute_for_users(
        self,
        user_ids: Sequence[int],
        *,
        weeks: int,
        week_start: date | None = None,
        force: bool = False,
        locale: str = "ru",
    ) -> tuple[int, int, int]:
        total_updated = 0
        total_debounced = 0
        total_empty = 0
        for user_id in user_ids:
            updated, debounced, empty = await self.ensure_range(
                user_id,
                weeks=weeks,
                week_start=week_start,
                force=force,
                locale=locale,
            )
            total_updated += updated
            total_debounced += debounced
            total_empty += empty
        return total_updated, total_debounced, total_empty

    async def _recompute_single(
        self,
        *,
        user_id: int,
        week_start: date,
        force: bool,
        locale: str,
    ) -> str:
        now = self._clock()
        normalized = self._normalize_week_start(week_start)
        key = (user_id, normalized)
        existing = await self._storage.get_weekly_insight(user_id, normalized)

        last_run: datetime | None
        if existing is not None:
            last_run = existing.computed_at
        else:
            cached = self._recent_runs.get(key)
            if cached and (now - cached).total_seconds() < self._debounce_seconds:
                last_run = cached
            else:
                if cached:
                    self._recent_runs.pop(key, None)
                last_run = None

        if not force and last_run is not None:
            if (now - last_run).total_seconds() < self._debounce_seconds:
                return "debounced"

        start_dt = datetime.combine(normalized, datetime.min.time())
        end_dt = start_dt + timedelta(days=7)
        activity = await self._storage.fetch_activity_range(user_id, start_dt, end_dt)
        emotions = activity["emotions"]
        journals = activity["journals"]

        if not emotions and not journals:
            if existing is None:
                self._recent_runs[key] = now
                return "empty"
            aggregate = self._empty_aggregate(normalized)
        else:
            aggregate = self._compute_aggregate(normalized, emotions, journals, locale)

        summary, summary_model, summary_source = await self._maybe_enrich_summary(
            user_id=user_id,
            locale=locale,
            aggregate=aggregate,
        )

        await self._storage.save_weekly_insight(
            user_id=user_id,
            week_start=normalized,
            week_end=aggregate["week_end"],
            mood_avg=aggregate["mood_avg"],
            mood_volatility=aggregate["mood_volatility"],
            top_emotions=aggregate["top_emotions"],
            journal_wordcloud=aggregate["wordcloud"],
            days_with_entries=aggregate["days_with_entries"],
            longest_streak=aggregate["longest_streak"],
            entries_count=aggregate["entries_count"],
            entries_by_day=aggregate["entries_by_day"],
            summary=summary,
            summary_model=summary_model,
            summary_source=summary_source,
            computed_at=now,
        )
        self._recent_runs[key] = now
        return "updated"

    async def _maybe_enrich_summary(
        self,
        *,
        user_id: int,
        locale: str,
        aggregate: dict[str, object],
    ) -> tuple[str | None, str | None, str | None]:
        router = self._ai_router
        if router is None:
            return None, None, None
        try:
            prompt = self._build_summary_prompt(aggregate, locale)
            response: AIResponse = await router.ask(
                user_id=user_id,
                kind="weekly_review",
                text=prompt,
                locale=locale,
                use_cache=True,
            )
        except Exception:  # pragma: no cover - defensive against optional dependency issues
            return None, None, None
        return response.text, response.model, response.source

    @staticmethod
    def _normalize_week_start(value: date) -> date:
        return value - timedelta(days=value.weekday())

    def _compute_aggregate(
        self,
        week_start: date,
        emotions: Sequence,
        journals: Sequence,
        locale: str,
    ) -> dict[str, object]:
        week_end = week_start + timedelta(days=6)
        intensities = [entry.intensity for entry in emotions]
        mood_avg = round(sum(intensities) / len(intensities), 2) if intensities else None
        mood_volatility = None
        if intensities:
            mean_intensity = mood_avg or 0
            variance = sum(
                (value - mean_intensity) ** 2 for value in intensities
            ) / len(intensities)
            mood_volatility = round(math.sqrt(variance), 2)

        counter = Counter(entry.emotion_code for entry in emotions)
        top_emotions = []
        for code, count in counter.most_common(5):
            emotion_intensities = [
                entry.intensity
                for entry in emotions
                if entry.emotion_code == code
            ]
            avg_intensity = (
                round(sum(emotion_intensities) / len(emotion_intensities), 2)
                if emotion_intensities
                else None
            )
            top_emotions.append(
                {"code": code, "count": count, "avg_intensity": avg_intensity}
            )

        wordcloud = self._build_wordcloud(journals, locale)
        entry_dates = {
            entry.created_at.date() for entry in (*emotions, *journals)
        }
        daily_counts = Counter(
            entry.created_at.date().weekday() for entry in (*emotions, *journals)
        )
        days_with_entries = len(entry_dates)
        longest_streak = self._compute_longest_streak(entry_dates)
        entries_count = len(emotions) + len(journals)

        entries_by_day = [
            {"day": index, "count": daily_counts.get(index, 0)} for index in range(7)
        ]

        return {
            "week_start": week_start,
            "week_end": week_end,
            "mood_avg": mood_avg,
            "mood_volatility": mood_volatility,
            "top_emotions": top_emotions,
            "wordcloud": wordcloud,
            "days_with_entries": days_with_entries,
            "longest_streak": longest_streak,
            "entries_count": entries_count,
            "entries_by_day": entries_by_day,
        }

    @staticmethod
    def _empty_aggregate(week_start: date) -> dict[str, object]:
        week_end = week_start + timedelta(days=6)
        return {
            "week_start": week_start,
            "week_end": week_end,
            "mood_avg": None,
            "mood_volatility": None,
            "top_emotions": [],
            "wordcloud": [],
            "days_with_entries": 0,
            "longest_streak": 0,
            "entries_count": 0,
            "entries_by_day": [
                {"day": index, "count": 0}
                for index in range(7)
            ],
        }

    @staticmethod
    def _compute_longest_streak(entry_dates: Iterable[date]) -> int:
        if not entry_dates:
            return 0
        streak = 1
        longest = 1
        sorted_dates = sorted(entry_dates)
        for previous, current in pairwise(sorted_dates):
            if current == previous + timedelta(days=1):
                streak += 1
                longest = max(longest, streak)
            elif current != previous:
                streak = 1
        return longest

    def _build_wordcloud(self, journals: Sequence, locale: str) -> list[dict[str, object]]:
        words: Counter[str] = Counter()
        stopwords = _STOPWORDS_RU | _STOPWORDS_EN
        for entry in journals:
            tokens = _WORD_RE.findall(entry.entry_text.lower())
            for token in tokens:
                if len(token) < 3:
                    continue
                if token in stopwords:
                    continue
                words[token] += 1
        return [
            {"word": word, "count": count}
            for word, count in words.most_common(20)
        ]

    def _build_summary_prompt(self, aggregate: dict[str, object], locale: str) -> str:
        week_start: date = aggregate["week_start"]  # type: ignore[assignment]
        week_end: date = aggregate["week_end"]  # type: ignore[assignment]
        mood_avg = aggregate["mood_avg"]
        volatility = aggregate["mood_volatility"]
        days = aggregate["days_with_entries"]
        longest = aggregate["longest_streak"]
        top_emotions = aggregate["top_emotions"]
        words = aggregate["wordcloud"]
        entries = aggregate["entries_count"]

        range_label = f"{week_start.isoformat()} — {week_end.isoformat()}"
        emotion_summary = ", ".join(
            f"{item['code']}×{item['count']}" for item in top_emotions[:3]
        ) or "none"
        keywords = ", ".join(item["word"] for item in words[:5]) if words else ""
        locale_norm = locale if locale in {"ru", "en"} else "ru"
        if locale_norm == "ru":
            prompt = (
                "Сформируй тёплое резюме недели пользователя. "
                "Формат: 3 предложения, до 90 слов, без советов."
            )
            prompt += (
                f"\nНеделя: {range_label}. Записей: {entries}. "
                f"Дней с активностью: {days}, серия: {longest}."
            )
            prompt += (
                f"\nСредняя интенсивность: {mood_avg or '–'}, "
                f"волатильность: {volatility or '–'}."
            )
            if emotion_summary:
                prompt += f"\nЭмоции: {emotion_summary}."
            if keywords:
                prompt += f"\nКлючевые слова: {keywords}."
            prompt += "\nПодчеркни моменты опоры и мягкий вывод."
        else:
            prompt = (
                "Craft a gentle three-sentence weekly reflection under 90 words. "
                "Avoid direct advice, highlight support moments."
            )
            prompt += (
                f"\nWeek: {range_label}. Entries: {entries}. "
                f"Active days: {days}, streak: {longest}."
            )
            prompt += (
                f"\nAverage mood: {mood_avg or '–'}, "
                f"volatility: {volatility or '–'}."
            )
            if emotion_summary:
                prompt += f"\nEmotions: {emotion_summary}."
            if keywords:
                prompt += f"\nKeywords: {keywords}."
            prompt += "\nClose with one anchoring thought."
        return prompt
