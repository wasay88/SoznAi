from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core import config
from backend.app.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_settings_read_version_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VERSION", "9.9.9")
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    monkeypatch.chdir(tmp_path)

    settings = get_settings()

    assert settings.version == "9.9.9"
    assert settings.bot_token == "token"
    assert str(settings.webapp_url) == "https://example.com/"
    assert settings.log_file.parent.exists()


def test_settings_fallback_to_version_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3", encoding="utf-8")
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.chdir(tmp_path)

    settings = get_settings()

    assert settings.version == "1.2.3"
    assert settings.log_file.parent.exists()
