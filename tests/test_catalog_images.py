from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from src.catalog_media import (
    MASTER_SIZE,
    THUMB_SIZE,
    catalog_media_path,
    process_catalog_image_bytes,
)


def test_process_catalog_image_bytes_crops_to_4x3() -> None:
    wide = Image.new("RGB", (1600, 900), (120, 80, 40))
    buffer = BytesIO()
    wide.save(buffer, format="JPEG")
    result = process_catalog_image_bytes(buffer.getvalue())
    assert result.width == MASTER_SIZE[0]
    assert result.height == MASTER_SIZE[1]
    assert len(result.master) > 1000
    assert len(result.thumb) > 500
    with Image.open(BytesIO(result.master)) as master:
        assert master.size == MASTER_SIZE
    with Image.open(BytesIO(result.thumb)) as thumb:
        assert thumb.size == THUMB_SIZE


def test_catalog_media_path() -> None:
    assert catalog_media_path(7, "thumb") == "/catalog/media/7/thumb.jpg"
    assert catalog_media_path(7, "master") == "/catalog/media/7/master.jpg"
