from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from .config import Settings
from .db_storage import PostgresStorage

logger = logging.getLogger(__name__)


def build_daily_report_text(summary: dict[str, int]) -> str:
    return (
        "Ежедневная сводка за 24 часа\n"
        f"Новые обращения: {summary.get('new_leads', 0)}\n"
        f"Передано менеджеру: {summary.get('escalated', 0)}\n"
        f"Общая активность (сообщения): {summary.get('activity', 0)}"
    )


async def run_daily_reports(bot: Bot, settings: Settings, storage: PostgresStorage) -> None:
    while True:
        try:
            summary = await asyncio.to_thread(storage.get_daily_summary)
            text = build_daily_report_text(summary)
            await bot.send_message(chat_id=settings.telegram_chat_id, text=text, parse_mode=None)
        except TelegramAPIError:
            logger.exception("Telegram API error while sending daily report")
        except Exception:
            logger.exception("Daily report job failed")
        await asyncio.sleep(24 * 60 * 60)
