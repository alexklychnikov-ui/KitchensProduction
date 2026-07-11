from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.admin_web.auth import ensure_password_hash, hash_password, verify_password
from src.admin_web.config import AdminWebSettings
from src.admin_web.app import create_app

ADMIN_WEB_ROOT = Path(__file__).resolve().parents[1] / "src" / "admin_web"


def test_password_hash_roundtrip() -> None:
    stored = hash_password("secret-pass")
    assert verify_password("secret-pass", stored) is True
    assert verify_password("wrong", stored) is False


def _test_settings(tmp_path) -> AdminWebSettings:
    return AdminWebSettings(
        database_url=os.getenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:5433/test"),
        admin_user="admin",
        admin_password="test-pass",
        session_secret="test-session-secret-key-32bytes!!",
        host="127.0.0.1",
        port=8081,
        uploads_dir=tmp_path / "uploads",
        static_dir=ADMIN_WEB_ROOT / "static",
        templates_dir=ADMIN_WEB_ROOT / "templates",
    )


@pytest.fixture()
def client(tmp_path) -> TestClient:
    settings = _test_settings(tmp_path)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    with patch("src.admin_web.app.AdminRepository") as repo_cls:
        repo = MagicMock()
        repo.ensure_schema.return_value = None
        repo.list_settings.return_value = {
            "timezone": "Asia/Irkutsk",
            "brand_name": "АртКухня",
            "brand_city": "Иркутск",
        }
        repo.get_summary.return_value = {
            "new_leads": 1,
            "escalated": 0,
            "activity": 3,
            "faq_count": 5,
            "catalog_count": 9,
            "orders_count": 2,
            "new_orders": 1,
        }
        repo.list_orders.return_value = [
            {"id": 1, "phone": "+7999", "estimate_total": 150000, "created_at": "2026-07-11T10:00:00"}
        ]
        repo.get_order.return_value = {
            "id": 1,
            "phone": "+7999",
            "status": "new",
            "estimate_total": 150000,
            "created_at": "2026-07-11T10:00:00",
        }
        repo.list_order_dialogs.return_value = [{"source": "text", "text": "привет", "created_at": "2026-07-11T10:00:00"}]
        repo.get_admin_password_hash.return_value = ensure_password_hash("test-pass")
        repo.is_password_changed.return_value = True
        repo_cls.return_value = repo
        app = create_app(settings)
        return TestClient(app)


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_login_flow(client: TestClient) -> None:
    res = client.get("/login")
    assert res.status_code == 200
    bad = client.post("/login", data={"username": "admin", "password": "bad"}, follow_redirects=False)
    assert bad.status_code == 401
    ok = client.post("/login", data={"username": "admin", "password": "test-pass"}, follow_redirects=False)
    assert ok.status_code == 302
    dash = client.get("/")
    assert dash.status_code == 200


def test_change_password(client: TestClient) -> None:
    client.post("/login", data={"username": "admin", "password": "test-pass"}, follow_redirects=False)
    ok = client.post(
        "/api/change-password",
        json={"current_password": "test-pass", "new_password": "new1234", "confirm_password": "new1234"},
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


def test_orders_api(client: TestClient) -> None:
    client.post("/login", data={"username": "admin", "password": "test-pass"}, follow_redirects=False)
    res = client.get("/api/orders")
    assert res.status_code == 200
    assert res.json()[0]["id"] == 1
    detail = client.get("/api/orders/1")
    assert detail.status_code == 200
    assert detail.json()["order"]["id"] == 1
    assert detail.json()["dialogs"]

