from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart, StateFilter
from aiogram.enums import ChatType
from aiogram.types import Message

from .admin_wizard import AdminStates, register_admin_handlers
from .config import Settings
from .escalation import after_hours_note, evaluate_escalation, should_escalate
from .funnel import (
    FunnelState,
    filter_escalation_keywords,
    idle_offer_keyboard,
    idle_offer_text,
    answer_wizard_question,
    process_idle_message,
    process_wizard_text,
    request_manager_contact,
    wants_to_start_order,
)
from .funnel_handlers import register_funnel_handlers, send_funnel_result, _keyboard_markup
from .pricing import maybe_calculate_price
from .storage import StorageBackend
from .stt_proxyapi import transcribe_voice_file

logger = logging.getLogger(__name__)

FALLBACK_RESPONSE = (
    "Могу провести подбор кухни по шагам или ответить на вопрос. "
    "Нажмите «Подобрать кухню» или напишите, что интересует."
)
ESCALATION_RESPONSE = (
    "Передал ваш запрос менеджеру. Скоро с вами свяжется специалист."
)
WELCOME_MESSAGE = (
    "Здравствуйте! Я бот студии «АртКухня» 🙂\n"
    "Помогу подобрать кухню по шагам — стиль, фасады, столешница, фурнитура — "
    "дам ориентир по стоимости и запишу на бесплатный замер."
)
GREETING_RESPONSE = (
    "Рад вас видеть! Нажмите «Подобрать кухню» — проведу по шагам, "
    "или спросите про сроки, материалы и доставку."
)


def _command_args(message: Message, command: str) -> str:
    text = (message.text or "").strip()
    if not text:
        return ""
    token, _, rest = text.partition(" ")
    if token.split("@", 1)[0] != command:
        return ""
    return rest.strip()


def _is_command(text: str | None, command: str) -> bool:
    if not text:
        return False
    return text.split()[0].split("@")[0] == command


def _is_start_command(text: str | None) -> bool:
    if not text:
        return False
    token = text.strip().split()[0].split("@")[0].lower()
    return token in {"/start", "/старт"}


def _is_private_chat(message: Message) -> bool:
    return message.chat.type == ChatType.PRIVATE


def _is_client_text(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    return not text.strip().startswith("/")


def _is_greeting(text: str) -> bool:
    normalized = text.lower().strip().rstrip("!?.")
    first = normalized.split()[0] if normalized.split() else ""
    greetings = {
        "привет",
        "здравствуйте",
        "здравствуй",
        "добрый",
        "доброе",
        "hello",
        "hi",
        "хай",
        "салам",
    }
    return first in greetings or normalized in greetings


def _faq_answer(storage: StorageBackend, text: str) -> str:
    answer = storage.get_faq_answer(text)
    return answer or FALLBACK_RESPONSE


def register_handlers(dp: Dispatcher, bot: Bot, settings: Settings, storage: StorageBackend) -> None:
    def _is_admin(user_id: int) -> bool:
        return bool(settings.admin_ids) and user_id in settings.admin_ids

    async def _reply(message: Message, user_id: int, text: str) -> None:
        await message.answer(text, parse_mode=None)
        storage.add_event(user_id=user_id, event_type="bot_reply", payload={"text": text[:300]})

    async def _reply_customer(message: Message, user_id: int, text: str) -> None:
        note = after_hours_note()
        if note:
            text = f"{text}{note}"
        await _reply(message, user_id, text)

    def _funnel_context() -> dict[str, object]:
        uploads_dir = str(settings.catalog_uploads_dir) if settings.catalog_uploads_dir else None
        return {
            "catalog_lookup": storage.list_catalog,
            "pricing_reference": storage.get_pricing_reference(),
            "faq_lookup": storage.get_faq_answer,
            "public_base_url": settings.catalog_public_base_url,
            "uploads_dir": uploads_dir,
        }

    async def _handle_start(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_private_chat(message):
            await message.answer(
                "Я отвечаю в личных сообщениях. Откройте бота и нажмите Start.",
                parse_mode=None,
            )
            return
        logger.info("Start from user_id=%s chat_id=%s", user_id, message.chat.id)
        storage.add_event(user_id=user_id, event_type="session_start", payload={})
        storage.clear_funnel_state(user_id)
        note = after_hours_note()
        welcome = WELCOME_MESSAGE + (note or "")
        await message.answer(
            welcome,
            reply_markup=_keyboard_markup(idle_offer_keyboard()),
            parse_mode=None,
        )
        storage.add_event(user_id=user_id, event_type="bot_reply", payload={"text": welcome[:300]})

    @dp.message(CommandStart(deep_link=True, ignore_mention=True))
    async def handle_start_deeplink(message: Message) -> None:
        await _handle_start(message)

    @dp.message(CommandStart(ignore_mention=True))
    async def handle_start_command(message: Message) -> None:
        await _handle_start(message)

    @dp.message(F.text.func(_is_start_command))
    async def handle_start_text(message: Message) -> None:
        await _handle_start(message)

    register_admin_handlers(dp, settings, storage)
    register_funnel_handlers(dp, bot, settings, storage)

    @dp.message(F.text.func(lambda t: _is_command(t, "/cfg_faq_set")))
    async def handle_cfg_faq_set(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(user_id):
            await _reply(message, user_id, "Команда доступна только администратору.")
            return
        text = _command_args(message, "/cfg_faq_set")
        parts = [p.strip() for p in text.split("|", maxsplit=1)]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            await _reply(message, user_id, "Формат: /cfg_faq_set key|answer\nИли откройте /admin")
            return
        key, answer = parts
        storage.admin_set_faq(user_id, key, answer)
        await _reply(message, user_id, f"FAQ обновлен: {key}")

    @dp.message(F.text.func(lambda t: _is_command(t, "/cfg_escalation_set")))
    async def handle_cfg_escalation_set(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(user_id):
            await _reply(message, user_id, "Команда доступна только администратору.")
            return
        text = _command_args(message, "/cfg_escalation_set")
        parts = [p.strip() for p in text.split("|", maxsplit=1)]
        if len(parts) != 2:
            await _reply(message, user_id, "Формат: /cfg_escalation_set keyword|on|off\nИли откройте /admin")
            return
        keyword, state = parts
        is_active = state.lower() in {"on", "1", "true", "yes"}
        storage.admin_set_escalation_keyword(user_id, keyword, is_active)
        await _reply(message, user_id, f"Триггер '{keyword}' -> {'on' if is_active else 'off'}")

    @dp.message(F.text.func(lambda t: _is_command(t, "/cfg_fee_set")))
    async def handle_cfg_fee_set(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(user_id):
            await _reply(message, user_id, "Команда доступна только администратору.")
            return
        text = _command_args(message, "/cfg_fee_set")
        parts = [p.strip() for p in text.split("|", maxsplit=1)]
        if len(parts) != 2:
            await _reply(message, user_id, "Формат: /cfg_fee_set code|value\nИли откройте /admin")
            return
        code, value_raw = parts
        try:
            value = float(value_raw.replace(",", "."))
        except ValueError:
            await _reply(message, user_id, "Value должно быть числом. Пример: /cfg_fee_set assembly_min|15000")
            return
        storage.admin_set_service_fee(user_id, code, value)
        await _reply(message, user_id, f"Fee '{code}' обновлен: {value}")

    async def _process_customer_message(
        message: Message,
        user_id: int,
        text: str,
        *,
        progress_event: str | None = None,
    ) -> None:
        keywords = storage.get_escalation_keywords()
        state = FunnelState.from_dict(storage.get_funnel_state(user_id))
        ctx = _funnel_context()

        if state.is_active():
            new_state, funnel_result = process_wizard_text(text, state, **ctx)
            if funnel_result.handled:
                if funnel_result.progress_made:
                    storage.set_funnel_state(user_id, new_state.to_dict())
                    if progress_event:
                        storage.add_event(
                            user_id=user_id,
                            event_type=progress_event,
                            payload={"text": text[:300]},
                        )
                order_id = await send_funnel_result(
                    message=message,
                    user_id=user_id,
                    storage=storage,
                    result=funnel_result,
                    settings=settings,
                )
                if funnel_result.should_escalate:
                    summary = funnel_result.escalation_summary
                    if order_id is not None:
                        summary = f"{summary}\nЗаказ №{order_id}"
                    reasons = funnel_result.escalation_reasons or ["order_created"]
                    await _send_escalation(
                        bot=bot,
                        settings=settings,
                        storage=storage,
                        message=message,
                        user_id=user_id,
                        source_text=summary,
                        reasons=reasons,
                    )
                return
            qa_state, qa_result = answer_wizard_question(text, state, **ctx)
            if qa_result.handled:
                await send_funnel_result(
                    message=message,
                    user_id=user_id,
                    storage=storage,
                    result=qa_result,
                    settings=settings,
                )
                return

        if _is_greeting(text) and not should_escalate(text, keywords):
            note = after_hours_note()
            reply = GREETING_RESPONSE + (note or "")
            await message.answer(
                reply,
                reply_markup=_keyboard_markup(idle_offer_keyboard()),
                parse_mode=None,
            )
            storage.add_event(user_id=user_id, event_type="bot_reply", payload={"text": reply[:300]})
            return

        filtered_keywords = filter_escalation_keywords(keywords, text)
        decision = evaluate_escalation(
            text=text,
            keywords=filtered_keywords,
            has_attachments=False,
            bot_message_count=storage.get_session_bot_message_count(user_id),
            user_message_count=storage.get_session_user_message_count(user_id),
        )
        if decision.should_escalate:
            state = FunnelState.from_dict(storage.get_funnel_state(user_id))
            if not state.phone:
                manager_state, manager_result = request_manager_contact(state)
                storage.set_funnel_state(user_id, manager_state.to_dict())
                if manager_result.should_escalate:
                    order_id = await send_funnel_result(
                        message=message,
                        user_id=user_id,
                        storage=storage,
                        result=manager_result,
                        settings=settings,
                    )
                    summary = manager_result.escalation_summary
                    if order_id is not None:
                        summary = f"{summary}\nЗаказ №{order_id}"
                    reasons = manager_result.escalation_reasons or ["manager_requested"]
                    await _send_escalation(
                        bot=bot,
                        settings=settings,
                        storage=storage,
                        message=message,
                        user_id=user_id,
                        source_text=summary,
                        reasons=reasons,
                    )
                else:
                    await _reply_customer(message, user_id, manager_result.text)
                return
            await _send_escalation(
                bot=bot,
                settings=settings,
                storage=storage,
                message=message,
                user_id=user_id,
                source_text=text,
                reasons=decision.reasons,
            )
            await _reply_customer(message, user_id, ESCALATION_RESPONSE)
            return

        started = process_idle_message(text, state, **ctx)
        if started is not None:
            new_state, funnel_result = started
            storage.set_funnel_state(user_id, new_state.to_dict())
            await send_funnel_result(
                message=message,
                user_id=user_id,
                storage=storage,
                result=funnel_result,
                settings=settings,
            )
            return

        pricing_result = maybe_calculate_price(text, storage.get_pricing_reference())
        if pricing_result.matched:
            storage.add_event(
                user_id=user_id,
                event_type="price_estimate",
                payload={"input_text": text},
            )
            await _reply_customer(message, user_id, pricing_result.text)
            return

        faq = _faq_answer(storage, text)
        if faq == FALLBACK_RESPONSE or wants_to_start_order(text):
            note = after_hours_note()
            reply = f"{faq}\n\n{idle_offer_text()}" + (note or "")
            await message.answer(
                reply,
                reply_markup=_keyboard_markup(idle_offer_keyboard()),
                parse_mode=None,
            )
            storage.add_event(user_id=user_id, event_type="bot_reply", payload={"text": reply[:300]})
            return

        await _reply_customer(message, user_id, faq)

    @dp.message(F.text.func(_is_client_text), F.func(_is_private_chat), ~StateFilter(AdminStates))
    async def handle_text(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        text = (message.text or "").strip()
        if not text:
            return

        storage.add_request(user_id=user_id, text=text, source="text")
        storage.add_event(user_id=user_id, event_type="message_text", payload={"text": text})
        storage.reset_voice_retry_count(user_id)
        await _process_customer_message(message, user_id, text)

    @dp.message(F.photo | F.document, F.func(_is_private_chat), ~StateFilter(AdminStates))
    async def handle_attachments(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        raw_text = (message.caption or "").strip()
        text = raw_text or "Пользователь отправил вложение"
        storage.add_request(user_id=user_id, text=text, source="attachment")
        storage.add_event(user_id=user_id, event_type="message_attachment", payload={"text": text})
        decision = evaluate_escalation(
            text=text,
            keywords=storage.get_escalation_keywords(),
            has_attachments=True,
            bot_message_count=storage.get_session_bot_message_count(user_id),
            user_message_count=storage.get_session_user_message_count(user_id),
        )
        if decision.should_escalate:
            await _send_escalation(
                bot=bot,
                settings=settings,
                storage=storage,
                message=message,
                user_id=user_id,
                source_text=text,
                reasons=decision.reasons,
            )
            await _reply_customer(message, user_id, ESCALATION_RESPONSE)

    @dp.message(F.voice, F.func(_is_private_chat), ~StateFilter(AdminStates))
    async def handle_voice(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        storage.add_event(user_id=user_id, event_type="message_voice", payload={})

        if message.voice is None:
            await _reply(message, user_id, "Не удалось обработать голосовое сообщение. Попробуйте еще раз.")
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
            temp_path = Path(temp_file.name)

        try:
            await bot.download(message.voice, destination=temp_path)
            transcript = await transcribe_voice_file(temp_path, settings=settings)
            if not transcript:
                retry_count = storage.increment_voice_retry_count(user_id)
                if retry_count <= 1:
                    await _reply(
                        message,
                        user_id,
                        "Не до конца понял голосовое. Можете коротко повторить голосом или написать текстом?",
                    )
                    return
                await _send_escalation(
                    bot=bot,
                    settings=settings,
                    storage=storage,
                    message=message,
                    user_id=user_id,
                    source_text="Нераспознанное голосовое сообщение",
                    reasons=["stt_failed"],
                )
                await _reply_customer(message, user_id, ESCALATION_RESPONSE)
                return
            storage.reset_voice_retry_count(user_id)

            storage.add_request(user_id=user_id, text=transcript, source="voice")
            storage.add_event(
                user_id=user_id,
                event_type="voice_transcript",
                payload={"transcript": transcript},
            )

            await _process_customer_message(
                message,
                user_id,
                transcript,
                progress_event="voice_transcript",
            )
        except TelegramAPIError:
            logger.exception("Telegram API error while handling voice")
            await _reply(message, user_id, "Ошибка Telegram API при обработке голосового. Попробуйте чуть позже.")
        except Exception:
            logger.exception("STT error while handling voice")
            retry_count = storage.increment_voice_retry_count(user_id)
            if retry_count <= 1:
                await _reply(
                    message,
                    user_id,
                    "Не до конца понял голосовое. Можете коротко повторить голосом или написать текстом?",
                )
            else:
                await _send_escalation(
                    bot=bot,
                    settings=settings,
                    storage=storage,
                    message=message,
                    user_id=user_id,
                    source_text="Ошибка STT при обработке голосового",
                    reasons=["stt_failed"],
                )
                await _reply(message, user_id, ESCALATION_RESPONSE)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not delete temp file: %s", temp_path)


async def _send_escalation(
    bot: Bot,
    settings: Settings,
    storage: StorageBackend,
    message: Message,
    user_id: int,
    source_text: str,
    reasons: list[str],
) -> None:
    user = message.from_user
    username = f"@{user.username}" if user and user.username else "-"
    full_name = user.full_name if user else "-"
    resolved_user_id = user.id if user else user_id

    notify_text = (
        "Эскалация клиента\n"
        f"Пользователь: {full_name} ({username})\n"
        f"User ID: {resolved_user_id}\n"
        f"Причины: {', '.join(reasons)}\n"
        f"Сообщение: {source_text}"
    )
    try:
        await bot.send_message(chat_id=settings.telegram_chat_id, text=notify_text, parse_mode=None)
        storage.add_event(
            user_id=resolved_user_id,
            event_type="escalation_sent",
            payload={"reasons": reasons, "source_text": source_text[:300]},
        )
        asyncio.create_task(_send_sla_followup(bot, settings, notify_text))
    except TelegramAPIError:
        logger.exception("Telegram API error while sending escalation")


async def _send_sla_followup(bot: Bot, settings: Settings, notify_text: str) -> None:
    await asyncio.sleep(15 * 60)
    try:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=f"SLA-проверка 15 минут: проверьте обращение.\n\n{notify_text}",
            parse_mode=None,
        )
    except TelegramAPIError:
        logger.exception("Telegram API error while sending SLA follow-up")
