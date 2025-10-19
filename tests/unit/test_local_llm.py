from backend.app.ai.local_llm import generate_local_response


def test_local_llm_breathing() -> None:
    text = generate_local_response("breathing_hint", "подскажи", "ru")
    assert "дыхания" in text


def test_local_llm_default_en() -> None:
    text = generate_local_response("unknown", "anything", "en")
    assert "I'm here" in text


def test_local_llm_weekly_review() -> None:
    text = generate_local_response("weekly_review", "", "ru")
    assert "итоги" in text or "наблюдения" in text


def test_local_llm_deep_insight() -> None:
    text = generate_local_response("deep_insight", "", "en")
    assert "note" in text.lower()


def test_local_llm_weekly_review_en() -> None:
    text = generate_local_response("weekly_review", "", "en")
    assert "reflect" in text or "tomorrow" in text
