from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .config import get_settings


class JsonFormatter(logging.Formatter):
    """Serialize log records as JSON for structured ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in ("request_id", "path", "method", "status", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    settings = get_settings()
    log_path: Path = settings.log_file

    formatter = JsonFormatter()

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(formatter)
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
