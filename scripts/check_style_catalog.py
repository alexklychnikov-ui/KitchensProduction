#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.admin_web.repository import AdminRepository

if __name__ == "__main__":
    from src.admin_web.config import load_admin_settings

    repo = AdminRepository(load_admin_settings().database_url)
    repo.ensure_schema()
    items = repo.list_catalog("style")
    print(f"style_items={len(items)}")
    for item in items:
        print(item["code"], item.get("image_path") or "no image")
