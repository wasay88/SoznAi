from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

DEFAULT_SQLITE_URL = "sqlite:///./data/soznai.db"


def _serialize_row(row: dict[str, object]) -> dict[str, object]:
    serialized: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def export_sqlite(sqlite_url: str, output_path: Path) -> None:
    engine = create_engine(sqlite_url)
    payload: dict[str, list[dict[str, object]]] = {
        "journal": [],
        "emotions": [],
        "settings": [],
    }

    with engine.begin() as connection:
        for table in ("journal", "emotions", "settings"):
            result = connection.execute(text(f"SELECT * FROM {table} ORDER BY id"))
            rows = [
                _serialize_row(dict(row))
                for row in result.mappings()
            ]
            payload[table] = rows

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SoznAi data from SQLite to JSON")
    parser.add_argument("--sqlite-url", default=DEFAULT_SQLITE_URL, help="SQLite DATABASE_URL")
    parser.add_argument(
        "--output",
        default="data/soznai_export.json",
        type=Path,
        help="Path to export JSON file",
    )
    args = parser.parse_args()

    export_sqlite(args.sqlite_url, args.output)


if __name__ == "__main__":
    main()
