#!/usr/bin/env python3
from __future__ import annotations

import random
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from PIL import Image, ImageDraw, ImageFont

from src.admin_web.config import load_admin_settings
from src.admin_web.images import process_catalog_image, remove_catalog_image_files
from src.admin_web.repository import AdminRepository

CATEGORY_LABELS = {
    "style": "Стиль",
    "facade": "Фасад",
    "countertop": "Столешница",
    "hardware": "Фурнитура",
}

STYLE_BY_CODE: dict[str, dict[str, object]] = {
    "modern_wood": {"top": (36, 56, 96), "bottom": (176, 128, 72), "accent": (248, 248, 250)},
    "scandinavian": {"top": (252, 252, 254), "bottom": (220, 224, 228), "accent": (180, 186, 194)},
    "farmhouse": {"top": (72, 76, 82), "bottom": (196, 198, 202), "accent": (118, 120, 126)},
    "mdf_white": {"top": (248, 248, 250), "bottom": (220, 224, 228), "accent": (180, 186, 194)},
    "mdf_wood": {"top": (176, 128, 72), "bottom": (120, 78, 38), "accent": (92, 56, 28)},
    "enamel_grey": {"top": (176, 178, 182), "bottom": (118, 120, 126), "accent": (88, 90, 96)},
    "quartz": {"top": (236, 236, 238), "bottom": (196, 198, 202), "accent": (140, 142, 148)},
    "acrylic": {"top": (245, 238, 226), "bottom": (214, 198, 170), "accent": (168, 148, 118)},
    "ldsp": {"top": (222, 206, 176), "bottom": (186, 158, 112), "accent": (142, 112, 72)},
    "blum": {"top": (72, 108, 148), "bottom": (36, 56, 88), "accent": (210, 180, 60)},
    "hettich": {"top": (96, 104, 112), "bottom": (48, 52, 58), "accent": (220, 220, 224)},
    "boyard": {"top": (128, 92, 56), "bottom": (78, 52, 30), "accent": (230, 210, 170)},
}


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def _add_texture(image: Image.Image, accent: tuple[int, int, int], category: str) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    rng = random.Random(width + height)
    if category == "style":
        draw.rectangle([(0, int(height * 0.55)), (width, height)], fill=(28, 20, 14))
        for x in range(0, width, 40):
            draw.line([(x, 0), (x, int(height * 0.55))], fill=accent, width=1)
    elif category == "countertop":
        for _ in range(5000):
            x = rng.randint(0, width - 1)
            y = rng.randint(0, height - 1)
            shade = rng.randint(-18, 18)
            base = image.getpixel((x, y))
            dot = tuple(max(0, min(255, base[i] + shade)) for i in range(3))
            draw.point((x, y), fill=dot)
    elif category == "facade":
        if width > height:
            for x in range(0, width, 18):
                shade = rng.randint(-12, 12)
                draw.line([(x, 0), (x, height)], fill=tuple(max(0, min(255, accent[i] + shade)) for i in range(3)), width=2)
    elif category == "hardware":
        draw.ellipse([(width * 0.2, height * 0.2), (width * 0.8, height * 0.8)], outline=accent, width=8)
        draw.ellipse([(width * 0.32, height * 0.32), (width * 0.68, height * 0.68)], outline=(230, 230, 230), width=4)


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_sample(*, category: str, code: str, title: str) -> bytes:
    size = (1400, 1050)
    style = STYLE_BY_CODE.get(code, {"top": (200, 200, 200), "bottom": (120, 120, 120), "accent": (80, 80, 80)})
    image = _gradient(size, style["top"], style["bottom"])  # type: ignore[arg-type]
    _add_texture(image, style["accent"], category)  # type: ignore[arg-type]

    draw = ImageDraw.Draw(image)
    overlay_h = int(size[1] * 0.34)
    draw.rectangle([(0, size[1] - overlay_h), size], fill=(20, 14, 10))
    font_title = _load_font(56)
    font_sub = _load_font(30)
    category_label = CATEGORY_LABELS.get(category, category)
    draw.text((48, size[1] - overlay_h + 36), title, fill=(255, 248, 240), font=font_title)
    draw.text((48, size[1] - overlay_h + 108), f"{category_label} · АртКухня", fill=(212, 165, 116), font=font_sub)
    draw.text((48, size[1] - overlay_h + 150), "Тестовое фото", fill=(180, 170, 160), font=font_sub)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def main() -> None:
    settings = load_admin_settings()
    repo = AdminRepository(settings.database_url)
    repo.ensure_schema()
    uploads_dir = settings.uploads_dir
    uploads_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for category in ("style", "facade", "countertop", "hardware"):
        items = repo.list_catalog(category)
        for item in items:
            source = _render_sample(
                category=item["category"],
                code=item["code"],
                title=item["title"],
            )
            remove_catalog_image_files(
                uploads_dir,
                item.get("image_path"),
                item.get("image_thumb_path"),
            )
            processed = process_catalog_image(
                source_bytes=source,
                uploads_dir=uploads_dir,
                category=item["category"],
                code=item["code"],
            )
            repo.set_catalog_image(
                int(item["id"]),
                image_path=processed.public_master,
                image_thumb_path=processed.public_thumb,
                image_width=processed.width,
                image_height=processed.height,
            )
            print(f"OK {item['category']}/{item['code']} -> {processed.public_master}")
            total += 1
    print(f"seeded {total} catalog images")


if __name__ == "__main__":
    main()
