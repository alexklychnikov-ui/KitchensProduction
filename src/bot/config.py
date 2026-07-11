from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    proxy_api_key: str
    proxy_base_url: str
    openai_model_voice: str
    database_url: str | None
    admin_ids: tuple[int, ...]
    catalog_public_base_url: str | None
    catalog_uploads_dir: Path | None
    admin_dashboard_url: str


def _read_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def load_settings() -> Settings:
    load_dotenv()

    telegram_chat_id_raw = _read_required("TELEGRAM_CHAT_ID")
    try:
        telegram_chat_id = int(telegram_chat_id_raw)
    except ValueError as exc:
        raise ValueError("TELEGRAM_CHAT_ID must be an integer") from exc

    proxy_api_key = os.getenv("PROXY_API_KEY") or os.getenv("OPENAI_API_KEY")
    if proxy_api_key is None or not proxy_api_key.strip():
        raise ValueError(
            "Missing required environment variable: PROXY_API_KEY (or OPENAI_API_KEY fallback)"
        )

    admin_ids_raw = os.getenv("TELEGRAM_ADMIN_IDS", "").strip()
    admin_ids: tuple[int, ...] = ()
    if admin_ids_raw:
        parsed: list[int] = []
        for part in admin_ids_raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                parsed.append(int(part))
            except ValueError as exc:
                raise ValueError("TELEGRAM_ADMIN_IDS must contain comma-separated integers") from exc
        admin_ids = tuple(parsed)

    catalog_public_base_url = os.getenv("CATALOG_PUBLIC_BASE_URL", "").strip() or None
    uploads_raw = os.getenv("ADMIN_UPLOADS_DIR", "").strip()
    catalog_uploads_dir = Path(uploads_raw).resolve() if uploads_raw else None
    admin_dashboard_url = (
        os.getenv("ADMIN_DASHBOARD_URL", "").strip()
        or catalog_public_base_url
        or "https://kitchen.alexklyvibe.ru"
    )

    return Settings(
        telegram_bot_token=_read_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=telegram_chat_id,
        proxy_api_key=proxy_api_key.strip(),
        proxy_base_url=_read_required("PROXY_BASE_URL"),
        openai_model_voice=_read_required("OPENAI_MODEL_VOICE"),
        database_url=os.getenv("DATABASE_URL", "").strip() or None,
        admin_ids=admin_ids,
        catalog_public_base_url=catalog_public_base_url,
        catalog_uploads_dir=catalog_uploads_dir,
        admin_dashboard_url=admin_dashboard_url,
    )
