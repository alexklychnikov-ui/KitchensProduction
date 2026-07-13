from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from .config import Settings
from .escalation import prepare_escalation_reply
from .funnel import FunnelState, _build_escalation_summary
from .storage import StorageBackend

logger = logging.getLogger(__name__)


async def _resolve_user_identity(
    bot: Bot,
    storage: StorageBackend,
    user_id: int,
    row: dict[str, Any],
) -> tuple[str, str]:
    full_name = str(row.get("full_name") or "").strip()
    username = str(row.get("username") or "").strip().lstrip("@")

    if not full_name or not username:
        try:
            chat = await bot.get_chat(user_id)
            if chat.full_name:
                full_name = full_name or chat.full_name
            if chat.username:
                username = username or chat.username
            storage.ensure_lead_profile(
                user_id,
                full_name=chat.full_name,
                username=chat.username,
            )
        except TelegramAPIError:
            logger.warning("Could not resolve Telegram profile for user_id=%s", user_id)

    display_name = full_name or "—"
    display_user = f"@{username}" if username else "без @username"
    return display_name, display_user


async def process_abandoned_funnels(bot: Bot, settings: Settings, storage: StorageBackend) -> int:
    timeout = storage.get_managers_config().abandon_timeout_minutes
    stale = storage.list_stale_funnel_sessions(timeout_minutes=timeout)
    processed = 0
    for row in stale:
        user_id = int(row["user_id"])
        state = FunnelState.from_dict(row.get("state_json") or {})
        summary = _build_escalation_summary(
            state,
            header="Брошенная воронка — клиент не завершил подбор",
        )
        summary = f"{summary}\nШаг на момент ухода: {state.stage}"
        full_name, username = await _resolve_user_identity(bot, storage, user_id, row)

        client_text, notify_text, manager = prepare_escalation_reply(
            config=storage.get_managers_config(),
            timezone_name=storage.get_timezone(),
            reasons=["abandoned_funnel"],
            source_text=summary,
            full_name=full_name,
            username=username,
            user_id=user_id,
        )
        notify_text = (
            f"{notify_text}\n\n"
            "Клиент не завершил подбор. Решите, связываться ли с ним по частичным данным."
        )
        try:
            await bot.send_message(chat_id=settings.telegram_chat_id, text=notify_text, parse_mode=None)
        except TelegramAPIError:
            logger.exception("Failed to notify manager about abandoned funnel user_id=%s", user_id)
            continue

        storage.record_escalation_case(
            user_id=user_id,
            kind="abandoned_funnel",
            reasons=["abandoned_funnel"],
            summary=summary,
            funnel_snapshot=state.to_dict(),
            order_id=None,
            manager_id=manager.id,
            manager_name=manager.name,
            phone=state.phone,
            full_name=full_name if full_name != "—" else None,
            username=username if username != "без @username" else None,
            notified=True,
        )
        storage.mark_funnel_abandoned_escalated(user_id)
        storage.add_event(
            user_id=user_id,
            event_type="escalation_sent",
            payload={"reasons": ["abandoned_funnel"], "source_text": summary[:300]},
        )
        processed += 1
        logger.info("Abandoned funnel escalated user_id=%s stage=%s", user_id, state.stage)
    return processed


async def run_abandoned_funnel_watch(bot: Bot, settings: Settings, storage: StorageBackend) -> None:
    while True:
        try:
            count = await process_abandoned_funnels(bot, settings, storage)
            if count:
                logger.info("Abandoned funnel watch processed %s cases", count)
        except Exception:
            logger.exception("Abandoned funnel watch failed")
        await asyncio.sleep(60)
