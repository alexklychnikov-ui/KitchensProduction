from __future__ import annotations

from pathlib import Path

import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import StateFilter
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from .admin_wizard import AdminStates
from .config import Settings
from .funnel import (
    FunnelResult,
    FunnelState,
    _media_from_item,
    build_carousel_caption,
    build_carousel_header,
    carousel_keyboard,
    carousel_nav_result,
    start_wizard,
    apply_catalog_pick,
    apply_budget_pick,
    apply_shape_pick,
    confirm_estimate,
)
from .storage import StorageBackend

logger = logging.getLogger(__name__)


def _keyboard_markup(rows: list[list[tuple[str, str]]] | None) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def _step_context(storage: StorageBackend, settings: Settings) -> dict[str, object]:
    uploads_dir = str(settings.catalog_uploads_dir) if settings.catalog_uploads_dir else None
    return {
        "catalog_lookup": storage.list_catalog,
        "public_base_url": settings.catalog_public_base_url,
        "uploads_dir": uploads_dir,
    }


def _pick_context(storage: StorageBackend, settings: Settings) -> dict[str, object]:
    return {
        **_step_context(storage, settings),
        "pricing_reference": storage.get_pricing_reference(),
    }


async def _catalog_photo_source(
    item: dict[str, object],
    *,
    storage: StorageBackend,
    settings: Settings,
) -> str | FSInputFile | BufferedInputFile | None:
    if item.get("telegram_file_id"):
        return str(item["telegram_file_id"])

    item_id = item.get("id")
    getter = getattr(storage, "get_catalog_image_bytes", None)
    if getter and item_id is not None:
        raw = getter(int(item_id), "master")
        if raw:
            code = str(item.get("code") or "catalog")
            return BufferedInputFile(raw, filename=f"{code}.jpg")

    public_base_url = settings.catalog_public_base_url
    uploads_dir = str(settings.catalog_uploads_dir) if settings.catalog_uploads_dir else None
    _, url, path = _media_from_item(
        item,  # type: ignore[arg-type]
        public_base_url=public_base_url,
        uploads_dir=uploads_dir,
    )
    photo_path = Path(path) if path else None
    if photo_path and photo_path.exists():
        return FSInputFile(photo_path)
    if url:
        return url
    return None


async def _send_catalog_carousel(
    message: Message,
    *,
    result: FunnelResult,
    settings: Settings,
    storage: StorageBackend,
    edit: bool = False,
) -> None:
    category = result.carousel_category
    items = result.carousel_items or []
    if not category or not items:
        await message.answer(result.carousel_header or "Каталог пуст", parse_mode=None)
        return

    index = result.carousel_index
    header = result.carousel_header
    item = items[index]
    total = len(items)
    caption = build_carousel_caption(item, index=index, total=total, header=header)
    markup = _keyboard_markup(carousel_keyboard(category, items, index))

    media_source = await _catalog_photo_source(item, storage=storage, settings=settings)
    fid = media_source if isinstance(media_source, str) else None

    if edit and message.photo and media_source:
        try:
            edited = await message.edit_media(
                media=InputMediaPhoto(media=media_source, caption=caption),
                reply_markup=markup,
            )
            if edited.photo and not fid and item.get("id"):
                storage.set_catalog_telegram_file_id(int(item["id"]), edited.photo[-1].file_id)
            return
        except Exception:
            logger.exception("carousel edit_media failed category=%s index=%s", category, index)
        try:
            await message.edit_caption(caption=caption, reply_markup=markup)
            return
        except Exception:
            logger.exception("carousel edit_caption failed category=%s index=%s", category, index)

    if media_source:
        try:
            sent = await message.answer_photo(
                media_source,
                caption=caption,
                reply_markup=markup,
                parse_mode=None,
            )
            if sent.photo and not fid and item.get("id"):
                storage.set_catalog_telegram_file_id(int(item["id"]), sent.photo[-1].file_id)
            return
        except Exception:
            logger.exception("carousel photo send failed category=%s code=%s", category, item.get("code"))

    await message.answer(caption, reply_markup=markup, parse_mode=None)


async def send_funnel_result(
    *,
    message: Message,
    user_id: int,
    storage: StorageBackend,
    result: FunnelResult,
    settings: Settings | None = None,
    edit_carousel: bool = False,
) -> int | None:
    order_id: int | None = None
    if result.create_order and result.order_payload:
        order_id = storage.create_order(user_id, result.order_payload)

    if result.carousel_items and result.carousel_category and settings:
        await _send_catalog_carousel(
            message,
            result=result,
            settings=settings,
            storage=storage,
            edit=edit_carousel,
        )
        storage.add_event(
            user_id=user_id,
            event_type="bot_reply",
            payload={"text": (result.carousel_header or "")[:300], "carousel": result.carousel_category},
        )
        return order_id

    markup = _keyboard_markup(result.keyboard)
    note_kwargs: dict[str, object] = {"parse_mode": None}
    if markup is not None:
        note_kwargs["reply_markup"] = markup

    sent_photo = False
    photo_path = Path(result.photo_path) if result.photo_path else None

    if result.photo_file_id or result.photo_url or (photo_path and photo_path.exists()):
        try:
            if result.photo_file_id:
                await message.answer_photo(
                    result.photo_file_id,
                    caption=result.text,
                    **note_kwargs,
                )
            elif photo_path and photo_path.exists():
                sent = await message.answer_photo(
                    FSInputFile(photo_path),
                    caption=result.text,
                    **note_kwargs,
                )
                if sent.photo and result.catalog_item_id:
                    storage.set_catalog_telegram_file_id(result.catalog_item_id, sent.photo[-1].file_id)
            elif result.photo_url:
                sent = await message.answer_photo(
                    result.photo_url,
                    caption=result.text,
                    **note_kwargs,
                )
                if sent.photo and result.catalog_item_id:
                    storage.set_catalog_telegram_file_id(result.catalog_item_id, sent.photo[-1].file_id)
            sent_photo = True
        except Exception:
            sent_photo = False

    if not sent_photo:
        await message.answer(result.text, **note_kwargs)

    storage.add_event(user_id=user_id, event_type="bot_reply", payload={"text": result.text[:300]})
    return order_id


def register_funnel_handlers(
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    storage: StorageBackend,
) -> None:
    async def _persist_and_send(
        callback_or_message: CallbackQuery | Message,
        user_id: int,
        state: FunnelState,
        result: FunnelResult,
        *,
        edit_carousel: bool = False,
    ) -> None:
        if result.progress_made or result.handled:
            storage.set_funnel_state(user_id, state.to_dict())
        message = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
        if not message:
            return
        order_id = await send_funnel_result(
            message=message,
            user_id=user_id,
            storage=storage,
            result=result,
            settings=settings,
            edit_carousel=edit_carousel,
        )
        if result.should_escalate:
            from .handlers import _send_escalation

            summary = result.escalation_summary
            if order_id is not None:
                summary = f"{summary}\nЗаказ №{order_id}"
            await _send_escalation(
                bot=bot,
                settings=settings,
                storage=storage,
                message=message,
                user_id=user_id,
                source_text=summary,
                reasons=["order_created"],
            )

    @dp.callback_query(F.data == "fn:start", ~StateFilter(AdminStates))
    async def cb_funnel_start(callback: CallbackQuery) -> None:
        if not callback.from_user or not callback.message:
            return
        user_id = callback.from_user.id
        try:
            ctx = _step_context(storage, settings)
            state, result = start_wizard(FunnelState(), **ctx)
            await _persist_and_send(callback, user_id, state, result)
            await callback.answer()
        except Exception:
            logger.exception("funnel start failed user_id=%s", user_id)
            await callback.answer("Ошибка запуска подбора. Попробуйте /start", show_alert=True)

    @dp.callback_query(F.data.startswith("fn:nav:"), ~StateFilter(AdminStates))
    async def cb_funnel_nav(callback: CallbackQuery) -> None:
        if not callback.from_user or not callback.message or not callback.data:
            return
        user_id = callback.from_user.id
        parts = callback.data.split(":", 3)
        if len(parts) != 4:
            await callback.answer()
            return
        _, _, category, index_raw = parts
        try:
            index = int(index_raw)
        except ValueError:
            await callback.answer()
            return
        state = FunnelState.from_dict(storage.get_funnel_state(user_id))
        header = build_carousel_header(state, category)
        result = carousel_nav_result(
            category,
            index,
            catalog_lookup=storage.list_catalog,
            header=header,
        )
        await _persist_and_send(callback, user_id, state, result, edit_carousel=True)
        await callback.answer()

    @dp.callback_query(F.data == "fn:confirm:estimate", ~StateFilter(AdminStates))
    async def cb_funnel_confirm(callback: CallbackQuery) -> None:
        if not callback.from_user or not callback.message:
            return
        user_id = callback.from_user.id
        state = FunnelState.from_dict(storage.get_funnel_state(user_id))
        if state.stage != "estimate":
            await callback.answer("Сначала завершите подбор", show_alert=True)
            return
        state, result = confirm_estimate(state)
        await _persist_and_send(callback, user_id, state, result)
        await callback.answer()

    @dp.callback_query(F.data.startswith("fn:pick:"), ~StateFilter(AdminStates))
    async def cb_funnel_pick(callback: CallbackQuery) -> None:
        if not callback.from_user or not callback.message or not callback.data:
            return
        user_id = callback.from_user.id
        parts = callback.data.split(":", 3)
        if len(parts) != 4:
            await callback.answer()
            return
        _, _, category, code = parts
        ctx = _pick_context(storage, settings)
        state = FunnelState.from_dict(storage.get_funnel_state(user_id))

        if category == "shape":
            ctx = _pick_context(storage, settings)
            state, result = apply_shape_pick(
                state,
                code,
                catalog_lookup=storage.list_catalog,
                pricing_reference=ctx["pricing_reference"],  # type: ignore[arg-type]
                public_base_url=settings.catalog_public_base_url,
                uploads_dir=str(settings.catalog_uploads_dir) if settings.catalog_uploads_dir else None,
            )
            await _persist_and_send(callback, user_id, state, result)
            await callback.answer()
            return

        if category == "budget":
            product_classes = ctx.get("pricing_reference", {}).get("product_classes", {})  # type: ignore[union-attr]
            if code not in product_classes:
                await callback.answer("Класс недоступен", show_alert=True)
                return
            state, result = apply_budget_pick(state, code, **ctx)
            await _persist_and_send(callback, user_id, state, result)
            await callback.answer()
            return

        item = storage.get_catalog_item(category, code)
        if not item:
            await callback.answer("Позиция недоступна", show_alert=True)
            return
        state, result = apply_catalog_pick(state, category, code, item, **ctx)
        await _persist_and_send(callback, user_id, state, result)
        await callback.answer()
