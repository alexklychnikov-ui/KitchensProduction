#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from aiogram import Bot

from src.bot.config import load_settings


async def main() -> None:
    settings = load_settings()
    if not settings.admin_ids:
        raise SystemExit("TELEGRAM_ADMIN_IDS is empty")
    bot = Bot(token=settings.telegram_bot_token)
    text = (
        "✅ C+D готово\n\n"
        "• Дашборд: вкладка «Заявки» (список + деталь + диалог)\n"
        "• TG /admin: заявки, сводка, ссылка на веб-дашборд\n"
        "• FAQ/эскалация/сборы в TG → редирект на kitchen.alexklyvibe.ru"
    )
    for admin_id in settings.admin_ids:
        await bot.send_message(chat_id=admin_id, text=text, parse_mode=None)
    await bot.session.close()
    print(f"pinged {len(settings.admin_ids)} admin(s)")


if __name__ == "__main__":
    asyncio.run(main())
