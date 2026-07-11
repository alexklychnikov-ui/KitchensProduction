#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.bot.config import load_settings
from src.bot.db_storage import PostgresStorage


def main() -> None:
    settings = load_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL required")
    storage = PostgresStorage(settings.database_url)
    storage.ensure_schema_and_seed()
    print("schema ok")


if __name__ == "__main__":
    main()
