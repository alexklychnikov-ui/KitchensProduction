from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.filters import StateFilter
from aiogram.filters.logic import _InvertFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import User

from src.bot.admin_wizard import AdminStates, admin_router
from src.bot.admin_wizard import _COMMAND_REJECT_HINT
from src.bot.config import Settings
from src.bot.handlers import _is_client_text, register_handlers
from src.bot.storage import InMemoryStorage

ADMIN_ID = 1
BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789"


def _settings() -> Settings:
    return Settings(
        telegram_bot_token="x",
        telegram_chat_id=1,
        proxy_api_key="k",
        proxy_base_url="http://x",
        openai_model_voice="gpt",
        database_url=None,
        admin_ids=(ADMIN_ID,),
        catalog_public_base_url=None,
        catalog_uploads_dir=None,
        admin_dashboard_url="https://kitchen.alexklyvibe.ru",
    )


def _register() -> tuple[Dispatcher, Bot, InMemoryStorage]:
    memory = MemoryStorage()
    dp = Dispatcher(storage=memory)
    bot = Bot(token=BOT_TOKEN)
    register_handlers(dp, bot, _settings(), InMemoryStorage())
    return dp, bot, memory


def _admin_message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=User(id=ADMIN_ID, is_bot=False, first_name="Admin"),
        text=text,
        answer=AsyncMock(),
    )


def _handler(name: str):
    return next(h for h in admin_router.message.handlers if h.callback.__name__ == name)


def _fsm_context(memory: MemoryStorage, bot: Bot) -> FSMContext:
    key = StorageKey(bot_id=bot.id, chat_id=ADMIN_ID, user_id=ADMIN_ID)
    return FSMContext(storage=memory, key=key)


def _has_inverted_admin_state_filter(handler) -> bool:
    for filt in handler.filters:
        callback = filt.callback
        if isinstance(callback, _InvertFilter) and isinstance(callback.target.callback, StateFilter):
            if AdminStates in callback.target.callback.states:
                return True
    return False


@pytest.mark.parametrize(
    ("handler_name", "state", "state_data"),
    [
        ("faq_edit_text", AdminStates.faq_edit, {"faq_key": "цена", "faq_old": "old"}),
        ("faq_add_answer", AdminStates.faq_add_answer, {"faq_key": "акция"}),
        ("fee_edit_value", AdminStates.fee_edit, {"fee_code": "assembly_min", "fee_old": 12000.0}),
    ],
)
def test_fsm_text_handlers_reject_slash_commands(
    handler_name: str,
    state: AdminStates,
    state_data: dict,
) -> None:
    async def run() -> None:
        dp, bot, memory = _register()
        ctx = _fsm_context(memory, bot)
        await ctx.set_state(state)
        await ctx.update_data(**state_data)

        message = _admin_message("/admin_cancel")
        await _handler(handler_name).callback(message, ctx)

        message.answer.assert_awaited_once_with(_COMMAND_REJECT_HINT, parse_mode=None)
        assert await ctx.get_state() == state.state

    asyncio.run(run())


def test_fsm_faq_add_key_rejects_slash() -> None:
    async def run() -> None:
        dp, bot, memory = _register()
        ctx = _fsm_context(memory, bot)
        await ctx.set_state(AdminStates.faq_add_key)

        message = _admin_message("/help")
        await _handler("faq_add_key").callback(message, ctx)

        args, kwargs = message.answer.await_args
        assert "без команды" in args[0]
        assert kwargs.get("parse_mode") is None
        assert await ctx.get_state() == AdminStates.faq_add_key.state

    asyncio.run(run())


def test_user_handlers_skip_admin_fsm_state() -> None:
    async def run() -> None:
        inverted = ~StateFilter(AdminStates)
        assert await inverted(object(), raw_state=None) is True
        assert await inverted(object(), raw_state=AdminStates.faq_edit.state) is False
        assert await inverted(object(), raw_state=AdminStates.fee_edit.state) is False

    asyncio.run(run())


def test_user_message_handlers_registered_with_admin_state_guard() -> None:
    dp, bot, _ = _register()
    guarded = {"handle_text", "handle_attachments", "handle_voice"}
    found = {
        h.callback.__name__
        for h in dp.message.handlers
        if h.callback.__name__ in guarded and _has_inverted_admin_state_filter(h)
    }
    assert found == guarded


def test_handle_text_skips_slash_commands() -> None:
    dp, _, _ = _register()
    handle_text = next(h for h in dp.message.handlers if h.callback.__name__ == "handle_text")
    assert len(handle_text.filters) >= 2
    assert _is_client_text("/admin") is False
    assert _is_client_text("цена") is True
