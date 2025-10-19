from __future__ import annotations

from backend.app.services.peace import PeaceInput, compute_peace_score


def test_compute_peace_score_balanced_state() -> None:
    score = compute_peace_score(PeaceInput(mood=2, breath_per_minute=6, gratitude_entries=2))
    assert score == 0.783


def test_compute_peace_score_low_mood() -> None:
    score = compute_peace_score(PeaceInput(mood=-5, breath_per_minute=10, gratitude_entries=0))
    assert score == 0.18
