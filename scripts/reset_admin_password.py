#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import psycopg

from src.admin_web.auth import ensure_password_hash

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL missing")

password_hash = ensure_password_hash("1111")
with psycopg.connect(url) as conn, conn.cursor() as cur:
    cur.execute(
        """
        INSERT INTO app_settings(key, value)
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """,
        ("admin_password_hash", password_hash),
    )
    cur.execute("DELETE FROM app_settings WHERE key = %s", ("admin_password_changed",))

print("password reset to 1111")
