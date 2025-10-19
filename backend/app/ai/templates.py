from __future__ import annotations

# ruff: noqa: RUF001

TEMPLATE_MAP: dict[str, dict[str, list[str]]] = {
    "quick_tip": {
        "ru": [
            "Я рядом. Сначала выдох — медленно, чтобы плечи опустились.",
            "Давай по шагу: почувствуй стопы на полу, затем мягкий вдох на четыре.",
        ],
        "en": [
            "I'm here. First, let the breath out softly until your shoulders settle.",
            "One step at a time: notice your feet grounded, then a gentle four-count inhale.",
        ],
    },
    "breathing_hint": {
        "ru": [
            "Хочешь — сделаем цикл дыхания вместе: 1∕3 вдох, 2∕3 пауза, 3∕3 выдох.",
            "Три мягких круга: вдох 4, удержание 2, длинный выдох 6 — с закрытыми глазами.",
        ],
        "en": [
            "Let's take one soft cycle: 1⁄3 inhale, 2⁄3 pause, 3⁄3 exhale all the way out.",
            "Try three gentle rounds: inhale 4, hold 2, exhale 6 with your eyes resting closed.",
        ],
    },
    "mood_reply": {
        "ru": [
            "Отмечаю с тобой это чувство. Дышим мягко и оставляем его как маленький снимок.",
            "Спасибо, что поделился. Сохраняю мысль как камешек внимания и остаюсь рядом.",
        ],
        "en": [
            "I notice this feeling with you. Breathe softly and keep it as a tiny snapshot.",
            "Thank you for sharing. I keep it like a small stone of attention and stay close.",
        ],
    },
    "fallback": {
        "ru": [
            "Я рядом. Если нужно — тихо повторим дыхание и зафиксируем ощущение.",
        ],
        "en": [
            "I'm here. We can repeat the quiet breath and note the feeling whenever you like.",
        ],
    },
}


def choose_template(kind: str, locale: str = "ru") -> str:
    """Pick a template reply for the given kind/locale."""

    locale_norm = locale if locale in {"ru", "en"} else "ru"
    entries = TEMPLATE_MAP.get(kind) or TEMPLATE_MAP.get("fallback", {})
    options = entries.get(locale_norm) or entries.get("ru") or ["SoznAi рядом."]
    return options[0]
