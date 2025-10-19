from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from backend.app.core import config
from backend.app.core.logging import JsonFormatter, configure_logging


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_configure_logging_creates_handlers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "app.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.chdir(tmp_path)

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    try:
        configure_logging()
        handlers = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, RotatingFileHandler)
        ]
        assert handlers
        assert Path(handlers[0].baseFilename) == log_file

        handler_count = len(root_logger.handlers)
        configure_logging()
        assert len(root_logger.handlers) == handler_count
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_json_formatter_outputs_keys() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    output = formatter.format(record)
    payload = json.loads(output)
    assert payload["message"] == "hello"
    assert payload["request_id"] == "req-1"
    assert payload["level"] == "INFO"
