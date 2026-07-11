from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from src.bot.config import load_settings
    from src.bot.db_storage import PostgresStorage
    from src.bot.handlers import register_handlers
    from src.bot.abandoned_funnel import run_abandoned_funnel_watch
    from src.bot.reports import run_daily_reports
    from src.bot.storage import InMemoryStorage
else:
    from .config import load_settings
    from .db_storage import PostgresStorage
    from .handlers import register_handlers
    from .abandoned_funnel import run_abandoned_funnel_watch
    from .reports import run_daily_reports
    from .storage import InMemoryStorage


async def run() -> None:
    settings = load_settings()

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    report_task: asyncio.Task | None = None
    abandon_task: asyncio.Task | None = None
    if settings.database_url:
        storage = PostgresStorage(settings.database_url)
        storage.ensure_schema_and_seed()
        report_task = asyncio.create_task(run_daily_reports(bot, settings, storage))
        abandon_task = asyncio.create_task(run_abandoned_funnel_watch(bot, settings, storage))
    else:
        storage = InMemoryStorage()
    register_handlers(dp=dp, bot=bot, settings=settings, storage=storage)

    try:
        await dp.start_polling(bot)
    finally:
        if report_task is not None:
            report_task.cancel()
        if abandon_task is not None:
            abandon_task.cancel()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    try:
        asyncio.run(run())
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    except Exception:
        logging.exception("Fatal error during bot runtime")
        raise


if __name__ == "__main__":
    main()
