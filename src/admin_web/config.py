from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ADMIN_PASSWORD = "1111"


@dataclass(frozen=True)
class AdminWebSettings:
    database_url: str
    admin_user: str
    admin_password: str
    session_secret: str
    host: str
    port: int
    uploads_dir: Path
    static_dir: Path
    templates_dir: Path


def _read_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def load_admin_settings() -> AdminWebSettings:
    load_dotenv()
    base_dir = Path(__file__).resolve().parents[1]
    uploads = Path(os.getenv("ADMIN_UPLOADS_DIR", str(base_dir / "uploads"))).resolve()
    return AdminWebSettings(
        database_url=_read_required("DATABASE_URL"),
        admin_user=_read_required("ADMIN_DASHBOARD_USER"),
        admin_password=os.getenv("ADMIN_DASHBOARD_PASSWORD", DEFAULT_ADMIN_PASSWORD).strip()
        or DEFAULT_ADMIN_PASSWORD,
        session_secret=_read_required("ADMIN_SESSION_SECRET"),
        host=os.getenv("ADMIN_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(os.getenv("ADMIN_WEB_PORT", "8081")),
        uploads_dir=uploads,
        static_dir=Path(__file__).resolve().parent / "static",
        templates_dir=Path(__file__).resolve().parent / "templates",
    )
