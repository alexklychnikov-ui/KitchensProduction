from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageOps

ImageSize = Literal["thumb", "master"]

MASTER_SIZE = (1200, 900)
THUMB_SIZE = (400, 300)
TARGET_RATIO = 4 / 3
JPEG_QUALITY = 85
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ProcessedCatalogImageBytes:
    master: bytes
    thumb: bytes
    width: int
    height: int


def catalog_media_path(item_id: int, size: ImageSize = "thumb") -> str:
    return f"/catalog/media/{item_id}/{size}.jpg"


def catalog_media_url(item_id: int, size: ImageSize, base_url: str) -> str:
    return f"{base_url.rstrip('/')}{catalog_media_path(item_id, size)}"


def _crop_to_ratio(image: Image.Image, ratio: float) -> Image.Image:
    width, height = image.size
    current_ratio = width / height
    if abs(current_ratio - ratio) < 0.01:
        return image
    if current_ratio > ratio:
        new_width = int(height * ratio)
        left = (width - new_width) // 2
        return image.crop((left, 0, left + new_width, height))
    new_height = int(width / ratio)
    top = (height - new_height) // 2
    return image.crop((0, top, width, top + new_height))


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGB", "L"}:
        return image.convert("RGB")
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def _encode_jpeg(image: Image.Image, *, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def process_catalog_image_bytes(source_bytes: bytes) -> ProcessedCatalogImageBytes:
    if len(source_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("file too large")

    with Image.open(BytesIO(source_bytes)) as raw:
        image = ImageOps.exif_transpose(raw)
        image = _to_rgb(image)
        image = _crop_to_ratio(image, TARGET_RATIO)
        master = image.resize(MASTER_SIZE, Image.Resampling.LANCZOS)
        thumb = master.resize(THUMB_SIZE, Image.Resampling.LANCZOS)

    return ProcessedCatalogImageBytes(
        master=_encode_jpeg(master, quality=JPEG_QUALITY),
        thumb=_encode_jpeg(thumb, quality=82),
        width=MASTER_SIZE[0],
        height=MASTER_SIZE[1],
    )
