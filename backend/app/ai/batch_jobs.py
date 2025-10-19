from __future__ import annotations

# ruff: noqa: RUF001
from datetime import date, datetime, timedelta

from ..services.storage import StorageService
from .router import AIRouter


async def run_daily_insights(
    storage: StorageService,
    router: AIRouter,
    *,
    hours: int = 24,
    locale: str = "ru",
) -> int:
    """Aggregate recent activity and store daily insights per user."""

    since = datetime.utcnow() - timedelta(hours=hours)
    user_ids = await storage.list_recent_users(since)
    created = 0
    for user_id in user_ids:
        activity = await storage.fetch_recent_activity(user_id, since)
        emotions = activity["emotions"]
        journals = activity["journals"]
        if not emotions and not journals:
            continue
        emo_counter: dict[str, int] = {}
        for entry in emotions:
            emo_counter[entry.emotion_code] = emo_counter.get(entry.emotion_code, 0) + 1
        top_emotions = (
            ", ".join(f"{code}:{count}" for code, count in sorted(emo_counter.items())) or "нет"
        )
        prompt = (
            "Сформируй короткое (<=80 слов) человеческое наблюдение за последними 24 часами."
            " Укажи ключевые эмоции и поддерживающую мысль."
        )
        prompt += (
            f"\nЭмоций: {len(emotions)}, журналов: {len(journals)}, топ эмоции: {top_emotions}."
        )
        if journals:
            last_note = journals[-1].entry_text[:200]
            prompt += f"\nПоследняя запись: {last_note}"
        response = await router.ask(
            user_id=user_id,
            kind="weekly_review",
            text=prompt,
            locale=locale,
        )
        await storage.save_insight(user_id, date.today(), response.text)
        created += 1
    return created
