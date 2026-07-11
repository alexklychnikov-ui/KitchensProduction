#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.admin_web.config import load_admin_settings
from src.admin_web.images import process_catalog_image, remove_catalog_image_files
from src.admin_web.repository import AdminRepository

STYLE_FILES: dict[str, tuple[str, Path]] = {
    "modern_wood": ("modern_wood.png", Path("assets/styles/modern_wood.png")),
    "scandinavian": ("scandinavian.png", Path("assets/styles/scandinavian.png")),
    "farmhouse": ("farmhouse.png", Path("assets/styles/farmhouse.png")),
}


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    settings = load_admin_settings()
    repo = AdminRepository(settings.database_url)
    repo.ensure_schema()
    uploads_dir = settings.uploads_dir

    items = {item["code"]: item for item in repo.list_catalog("style")}
    missing = [code for code in STYLE_FILES if code not in items]
    if missing:
        raise SystemExit(f"catalog style items missing in DB: {missing}. Run ensure_schema first.")

    for code, (_, relative_path) in STYLE_FILES.items():
        source_path = base_dir / relative_path
        if not source_path.exists():
            raise SystemExit(f"image not found: {source_path}")

        item = items[code]
        source_bytes = source_path.read_bytes()
        remove_catalog_image_files(
            uploads_dir,
            item.get("image_path"),
            item.get("image_thumb_path"),
        )
        processed = process_catalog_image(
            source_bytes=source_bytes,
            uploads_dir=uploads_dir,
            category="style",
            code=code,
        )
        repo.set_catalog_image(
            int(item["id"]),
            image_path=processed.public_master,
            image_thumb_path=processed.public_thumb,
            image_width=processed.width,
            image_height=processed.height,
        )
        print(f"OK style/{code} <- {source_path.name}")

    print("style photos uploaded")


if __name__ == "__main__":
    main()
