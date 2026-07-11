#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg

from src.catalog_media import catalog_media_path


def main() -> int:
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 1

    uploads_dir = Path(os.getenv("ADMIN_UPLOADS_DIR", str(ROOT / "uploads"))).resolve()
    migrated = 0
    skipped = 0

    with psycopg.connect(database_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, category, code, image_path, image_thumb_path,
                   (image_thumb IS NOT NULL) AS has_bytes
            FROM catalog_items
            ORDER BY id
            """
        )
        rows = cur.fetchall()

        for item_id, category, code, image_path, image_thumb_path, has_bytes in rows:
            if has_bytes:
                skipped += 1
                continue

            master_file = _resolve_file(uploads_dir, image_path, category, code, "master.jpg")
            thumb_file = _resolve_file(uploads_dir, image_thumb_path, category, code, "thumb.jpg")
            if not master_file:
                skipped += 1
                continue

            master_bytes = master_file.read_bytes()
            thumb_bytes = thumb_file.read_bytes() if thumb_file else master_bytes
            cur.execute(
                """
                UPDATE catalog_items
                SET image_master = %s,
                    image_thumb = %s,
                    image_path = %s,
                    image_thumb_path = %s,
                    telegram_file_id = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    master_bytes,
                    thumb_bytes,
                    catalog_media_path(int(item_id), "master"),
                    catalog_media_path(int(item_id), "thumb"),
                    item_id,
                ),
            )
            migrated += 1
            print(f"migrated item #{item_id} {category}/{code}")

    print(f"done: migrated={migrated} skipped={skipped}")
    return 0


def _resolve_file(
    uploads_dir: Path,
    stored_path: str | None,
    category: str,
    code: str,
    fallback_name: str,
) -> Path | None:
    if stored_path and str(stored_path).startswith("/uploads/"):
        candidate = uploads_dir / str(stored_path).removeprefix("/uploads/")
        if candidate.exists():
            return candidate
    guessed = uploads_dir / "catalog" / str(category) / str(code) / fallback_name
    return guessed if guessed.exists() else None


if __name__ == "__main__":
    raise SystemExit(main())
