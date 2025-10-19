from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PeaceInput:
    """Data points that influence a peace score."""

    mood: int  # -5..5
    breath_per_minute: int  # breaths per minute
    gratitude_entries: int  # entries created today


def compute_peace_score(data: PeaceInput) -> float:
    """Compute a peace score between 0 and 1."""

    normalized_mood = (data.mood + 5) / 10  # 0..1
    breathing_component = max(0.0, min(1.0, 1 - abs(data.breath_per_minute - 6) / 10))
    gratitude_component = min(1.0, data.gratitude_entries / 3)

    score = 0.5 * normalized_mood + 0.3 * breathing_component + 0.2 * gratitude_component
    return round(score, 3)
