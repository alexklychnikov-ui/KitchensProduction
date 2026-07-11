from __future__ import annotations

from pathlib import Path

from src.catalog_media import (
    MASTER_SIZE,
    THUMB_SIZE,
    ProcessedCatalogImageBytes,
    catalog_media_path,
    process_catalog_image_bytes,
)

__all__ = [
    "MASTER_SIZE",
    "THUMB_SIZE",
    "ProcessedCatalogImageBytes",
    "catalog_media_path",
    "process_catalog_image_bytes",
    "remove_catalog_image_files",
]


def remove_catalog_image_files(uploads_dir: Path, image_path: str | None, thumb_path: str | None) -> None:
    for public_path in (image_path, thumb_path):
        if not public_path or not public_path.startswith("/uploads/"):
            continue
        relative = public_path.removeprefix("/uploads/")
        file_path = uploads_dir / relative
        if file_path.exists():
            file_path.unlink(missing_ok=True)
