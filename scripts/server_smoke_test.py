#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path("/opt/kitchens-bot")
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.bot.config import load_settings
from src.bot.db_storage import PostgresStorage
from src.bot.escalation import evaluate_escalation
from src.bot.pricing import maybe_calculate_price
from src.bot.storage import InMemoryStorage


def ok(name: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"[OK] {name}{suffix}")


def fail(name: str, detail: str) -> None:
    print(f"[FAIL] {name} — {detail}")
    sys.exit(1)


def main() -> None:
    settings = load_settings()
    ok("config", f"chat_id={settings.telegram_chat_id}, admins={settings.admin_ids}")

    storage = InMemoryStorage()

    faq = storage.get_faq_answer("сроки")
    if not faq:
        fail("faq_inmemory", "no answer for 'сроки'")
    ok("faq_inmemory", faq[:60])

    price = maybe_calculate_price("стоимость кухни 3 метра эконом", storage.get_pricing_reference())
    if not price.matched:
        fail("pricing", "no price for sample query")
    ok("pricing", price.text.splitlines()[0][:80])

    esc = evaluate_escalation(
        text="хочу поговорить с менеджером",
        keywords=storage.get_escalation_keywords(),
        has_attachments=False,
        bot_message_count=0,
        user_message_count=0,
    )
    if not esc.should_escalate:
        fail("escalation", "expected trigger on manager keyword")
    ok("escalation", ",".join(esc.reasons))

    if not settings.database_url:
        fail("postgres", "DATABASE_URL missing")
    pg = PostgresStorage(settings.database_url)
    pg.ensure_schema_and_seed()
    faq_pg = pg.get_faq_answer("гарантия")
    if not faq_pg:
        fail("postgres_seed", "no FAQ in DB")
    ok("postgres_seed", f"faq_items + tables ready")

    token = settings.telegram_bot_token
    import urllib.request

    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
        data = r.read().decode()
    if '"ok":true' not in data:
        fail("telegram_getMe", data[:200])
    ok("telegram_getMe")

    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/getChat?chat_id={settings.telegram_chat_id}",
        timeout=15,
    ) as r:
        chat_data = r.read().decode()
    if '"ok":true' not in chat_data:
        fail("telegram_getChat", chat_data[:200])
    ok("telegram_getChat", f"id={settings.telegram_chat_id}")

    proxy_url = settings.proxy_base_url.rstrip("/") + "/models"
    proxy_req = urllib.request.Request(
        proxy_url,
        headers={"Authorization": f"Bearer {settings.proxy_api_key}"},
    )
    try:
        with urllib.request.urlopen(proxy_req, timeout=15) as r:
            proxy_data = r.read(200).decode(errors="ignore")
        ok("proxyapi", f"HTTP reachable, sample={proxy_data[:40]}")
    except Exception as exc:
        fail("proxyapi", str(exc))

    print("SMOKE_ALL_OK")


if __name__ == "__main__":
    main()
