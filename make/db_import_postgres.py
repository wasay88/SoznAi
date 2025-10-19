from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

DEFAULT_OUTPUT_URL = "postgresql+psycopg://user:password@localhost:5432/soznai"


def _normalize_target_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def import_postgres(database_url: str, input_path: Path) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    engine = create_engine(_normalize_target_url(database_url))

    with engine.begin() as connection:
        for row in payload.get("journal", []):
            params = {
                "user_id": row.get("user_id"),
                "source": row.get("source") or "import",
                "entry_text": row.get("entry_text"),
                "created_at": _parse_timestamp(row.get("created_at")),
            }
            connection.execute(
                text(
                    """
                    INSERT INTO journal (
                        user_id,
                        source,
                        entry_text,
                        created_at
                    )
                    VALUES (
                        :user_id,
                        :source,
                        :entry_text,
                        coalesce(:created_at, NOW())
                    )
                    """
                ),
                params,
            )

        for row in payload.get("emotions", []):
            params = {
                "user_id": row.get("user_id"),
                "emotion_code": row.get("emotion_code"),
                "intensity": row.get("intensity"),
                "note": row.get("note"),
                "source": row.get("source") or "import",
                "created_at": _parse_timestamp(row.get("created_at")),
            }
            connection.execute(
                text(
                    """
                    INSERT INTO emotions (
                        user_id,
                        emotion_code,
                        intensity,
                        note,
                        source,
                        created_at
                    )
                    VALUES (
                        :user_id,
                        :emotion_code,
                        :intensity,
                        :note,
                        :source,
                        coalesce(:created_at, NOW())
                    )
                    """
                ),
                params,
            )

        for row in payload.get("settings", []):
            params = {
                "key": row.get("key"),
                "value": row.get("value"),
                "created_at": _parse_timestamp(row.get("created_at")),
            }
            connection.execute(
                text(
                    """
                    INSERT INTO settings (key, value, created_at)
                    VALUES (:key, :value, coalesce(:created_at, NOW()))
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """
                ),
                params,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import SoznAi data dump into PostgreSQL")
    parser.add_argument(
        "--input",
        default=Path("data/soznai_export.json"),
        type=Path,
        help="Path to JSON dump produced by db_export_sqlite.py",
    )
    parser.add_argument(
        "--database-url",
        default=DEFAULT_OUTPUT_URL,
        help="Target PostgreSQL DATABASE_URL (psycopg)",
    )
    args = parser.parse_args()

    import_postgres(args.database_url, args.input)


if __name__ == "__main__":
    main()
