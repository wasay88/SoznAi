from __future__ import annotations

# ruff: noqa: RUF001


def generate_local_response(kind: str, prompt: str, locale: str = "ru") -> str:
    """Return a deterministic local response as final fallback."""

    if kind in {"breathing_hint", "quick_tip"}:
        return (
            (
                "Сначала выдох. Давай мягко пройдём цикл дыхания: 1∕3 вдох, 2∕3 пауза, "
                "3∕3 выдох. Три круга."
            )
            if locale == "ru"
            else (
                "First, exhale. Move through a breath cycle: 1⁄3 inhale, 2⁄3 pause, "
                "3⁄3 exhale. Three calm rounds."
            )
        )
    if kind == "weekly_review":
        base = (
            "Сохраним наблюдения как серию снимков и мягко подведём итоги завтра."
            if locale == "ru"
            else "We'll keep these notes as gentle snapshots and reflect together tomorrow."
        )
        return base
    if kind == "deep_insight":
        return (
            "Запиши одну тёплую мысль, что поддерживает сейчас. Затем снова мягкий вдох."
            if locale == "ru"
            else "Write a warm note of what holds you now, then return to a soft breath."
        )
    return (
        "Я рядом. Сначала выдох, затем один спокойный шаг вперёд."
        if locale == "ru"
        else "I'm here. Start with an exhale, then a single gentle step forward."
    )
