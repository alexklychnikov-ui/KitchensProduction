from __future__ import annotations

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import Settings
from .orders import format_order_detail, format_order_short
from .reports import build_daily_report_text
from .storage import StorageBackend

admin_router = Router(name="admin_wizard")
_admin_handlers_registered = False

TELEGRAM_MESSAGE_MAX = 4096
_COMMAND_REJECT_HINT = "Команды в этом режиме не принимаются. Отмена: /admin_cancel"

FAQ_LABELS: dict[str, str] = {
    "цена": "Цена",
    "срок": "Сроки",
    "материал": "Материалы",
    "доставка": "Доставка",
    "гарантия": "Гарантия",
}

FEE_LABELS: dict[str, str] = {
    "delivery_city_free_threshold": "Бесплатная доставка от, ₽",
    "delivery_city_fixed": "Доставка по городу, ₽",
    "delivery_outside_base": "Доставка за город, база, ₽",
    "delivery_outside_per_km": "За км за город, ₽",
    "assembly_percent": "Монтаж, % от стоимости",
    "assembly_min": "Монтаж минимум, ₽",
}


class AdminStates(StatesGroup):
    faq_edit = State()
    faq_add_key = State()
    faq_add_answer = State()
    fee_edit = State()
    esc_add = State()


def _faq_label(key: str) -> str:
    return FAQ_LABELS.get(key, key.capitalize())


def _fee_label(code: str) -> str:
    return FEE_LABELS.get(code, code)


def _truncate(text: str, limit: int = 80) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _truncate_for_telegram(text: str, reserved: int = 200) -> str:
    limit = max(1, TELEGRAM_MESSAGE_MAX - reserved)
    compact = text
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _format_faq_saved_message(key: str, answer: str, old: str | None = None) -> str:
    if old is None:
        body = f"✅ FAQ добавлен: {_faq_label(key)}\n\n{answer}"
    else:
        body = (
            f"✅ Сохранено: {_faq_label(key)}\n\n"
            f"Было:\n{_truncate(old, 200)}\n\n"
            f"Стало:\n{answer}"
        )
    return _truncate_for_telegram(body, reserved=100)


def _build_faq_menu_text(items: list[tuple[str, str]]) -> str:
    lines = ["📋 FAQ — текущие ответы:\n"]
    for key, answer in items:
        line = f"• {_faq_label(key)}: {_truncate(answer)}"
        candidate = "\n".join([*lines, line])
        if len(candidate) + len("\n\nВыберите тему для изменения:") > TELEGRAM_MESSAGE_MAX - 50:
            lines.append("…")
            break
        lines.append(line)
    if not items:
        lines.append("Пока пусто.")
    lines.append("\nВыберите тему для изменения:")
    return _truncate_for_telegram("\n".join(lines), reserved=50)


def parse_fee_input(raw: str, code: str) -> tuple[float | None, str | None]:
    normalized = raw.strip().replace(",", ".")
    try:
        value = float(normalized)
    except ValueError:
        return None, "Введите число. Пример: 15000 или 15"
    if code == "assembly_percent":
        if value < 0 or value > 100:
            return None, "Процент монтажа должен быть от 0 до 100."
        return value / 100, None
    if value < 0:
        return None, "Значение не может быть отрицательным."
    return value, None


def _is_admin(settings: Settings, user_id: int) -> bool:
    return bool(settings.admin_ids) and user_id in settings.admin_ids


def _main_menu_kb(settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Заявки", callback_data="adm:orders")],
            [InlineKeyboardButton(text="📊 Сводка", callback_data="adm:sum")],
            [InlineKeyboardButton(text="🌐 Веб-дашборд", url=settings.admin_dashboard_url)],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:cancel")],
        ]
    )


def _orders_menu_kb(orders: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for order in orders[:10]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=format_order_short(order)[:60],
                    callback_data=f"adm:ord:{order['id']}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _legacy_redirect_kb(settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Веб-дашборд", url=settings.admin_dashboard_url)],
            [InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu")],
        ]
    )


def _legacy_config_hint() -> str:
    return (
        "Настройки FAQ, эскалации и прайса перенесены в веб-дашборд.\n"
        "Откройте «Веб-дашборд» в меню /admin."
    )



def _faq_menu_kb(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, (key, _answer) in enumerate(items):
        rows.append(
            [InlineKeyboardButton(text=f"✏️ {_faq_label(key)}", callback_data=f"adm:faq:i:{index}")]
        )
    rows.append([InlineKeyboardButton(text="➕ Добавить тему", callback_data="adm:faq:add")])
    rows.append(
        [
            InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _escalation_kb(items: list[tuple[str, bool]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, (keyword, active) in enumerate(items):
        mark = "✅" if active else "⬜"
        rows.append(
            [InlineKeyboardButton(text=f"{mark} {keyword}", callback_data=f"adm:esc:i:{index}")]
        )
    rows.append([InlineKeyboardButton(text="➕ Добавить слово", callback_data="adm:esc:add")])
    rows.append(
        [
            InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _fees_kb(items: list[tuple[str, float]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, (code, value) in enumerate(items):
        label = _fee_label(code)
        if code == "assembly_percent":
            value_text = f"{value * 100:.0f}%"
        else:
            value_text = f"{value:,.0f}".replace(",", " ")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {label}: {value_text}",
                    callback_data=f"adm:fee:i:{index}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_to_faq_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 FAQ", callback_data="adm:faq"),
                InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu"),
            ]
        ]
    )


async def _send_main_menu(message: Message, storage: StorageBackend, settings: Settings) -> None:
    orders_count = 0
    if hasattr(storage, "admin_list_orders"):
        orders_count = len(storage.admin_list_orders(limit=100))
    text = (
        "Операционная панель\n\n"
        f"Заявок в базе: {orders_count}\n\n"
        "Заявки и сводка — здесь.\n"
        "Настройки справочников — в веб-дашборде."
    )
    await message.answer(text, reply_markup=_main_menu_kb(settings), parse_mode=None)


def register_admin_handlers(
    dp: Dispatcher,
    settings: Settings,
    storage: StorageBackend,
) -> None:
    global _admin_handlers_registered
    if _admin_handlers_registered:
        return
    _admin_handlers_registered = True

    dp.include_router(admin_router)

    @admin_router.message(Command("admin", "admin_help"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(settings, user_id):
            await message.answer("Команда доступна только администратору.", parse_mode=None)
            return
        await state.clear()
        await _send_main_menu(message, storage, settings)

    @admin_router.message(Command("admin_cancel"))
    async def cmd_admin_cancel(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(settings, user_id):
            return
        await state.clear()
        await message.answer("Режим настройки закрыт.", parse_mode=None)

    @admin_router.callback_query(F.data == "adm:menu")
    async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            "Операционная панель\n\nЗаявки и сводка — здесь. Настройки — в веб-дашборде.",
            reply_markup=_main_menu_kb(settings),
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data == "adm:cancel")
    async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user and not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        if callback.message:
            await callback.message.edit_text("Режим настройки закрыт.", parse_mode=None)
        await callback.answer()

    @admin_router.callback_query(F.data == "adm:orders")
    async def cb_orders_menu(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        if not hasattr(storage, "admin_list_orders"):
            await callback.message.edit_text(
                "📋 Заявки доступны только при подключённой базе данных.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu")]]
                ),
                parse_mode=None,
            )
            await callback.answer()
            return
        orders = storage.admin_list_orders(limit=10)
        if not orders:
            await callback.message.edit_text(
                "📋 Заявок пока нет.\n\nКогда клиент пройдёт воронку до телефона — появится здесь.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu")]]
                ),
                parse_mode=None,
            )
            await callback.answer()
            return
        lines = ["📋 Последние заявки:\n"]
        for order in orders:
            lines.append(f"• {format_order_short(order)}")
        text = _truncate_for_telegram("\n".join(lines), reserved=80)
        await callback.message.edit_text(
            text,
            reply_markup=_orders_menu_kb(orders),
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data.regexp(r"^adm:ord:\d+$"))
    async def cb_order_detail(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user or not callback.data:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        if not hasattr(storage, "admin_get_order"):
            await callback.answer("БД не подключена", show_alert=True)
            return
        order_id = int(callback.data.rsplit(":", 1)[-1])
        order = storage.admin_get_order(order_id)
        if not order:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        dialogs = storage.admin_list_order_dialogs(order_id)
        text = _truncate_for_telegram(format_order_detail(order, dialogs), reserved=120)
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Заявки", callback_data="adm:orders")],
                    [InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu")],
                ]
            ),
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data == "adm:faq")
    async def cb_faq_menu(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            _legacy_config_hint(),
            reply_markup=_legacy_redirect_kb(settings),
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data == "adm:faq_legacy")
    async def cb_faq_menu_legacy(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        items = storage.admin_list_faq()
        await callback.message.edit_text(
            _build_faq_menu_text(items),
            reply_markup=_faq_menu_kb(items),
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data.regexp(r"^adm:faq:i:\d+$"))
    async def cb_faq_edit(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user or not callback.data:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        index = int(callback.data.rsplit(":", 1)[-1])
        items = storage.admin_list_faq()
        if index >= len(items):
            await callback.answer("Тема не найдена", show_alert=True)
            return
        key, _answer = items[index]
        answer = storage.admin_get_faq(key) or _answer
        await state.set_state(AdminStates.faq_edit)
        await state.update_data(faq_key=key, faq_old=answer)
        preview = _truncate_for_telegram(answer, reserved=120)
        await callback.message.edit_text(
            f"Тема: {_faq_label(key)}\n\n"
            f"Текущий ответ:\n{preview}\n\n"
            "Напишите новый текст одним сообщением.",
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data == "adm:faq:add")
    async def cb_faq_add(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.set_state(AdminStates.faq_add_key)
        await callback.message.edit_text(
            "Новая тема FAQ\n\n"
            "Шаг 1/2. Напишите ключевое слово — по нему бот поймёт вопрос.\n"
            "Пример: акция",
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.message(StateFilter(AdminStates.faq_add_key), F.text)
    async def faq_add_key(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(settings, user_id):
            return
        key = (message.text or "").strip().lower()
        if not key or key.startswith("/"):
            await message.answer(
                "Введите одно слово или короткую фразу без команды. Отмена: /admin_cancel",
                parse_mode=None,
            )
            return
        await state.update_data(faq_key=key)
        await state.set_state(AdminStates.faq_add_answer)
        await message.answer(
            f"Шаг 2/2. Тема: {_faq_label(key)}\n\nНапишите ответ бота для этой темы.",
            parse_mode=None,
        )

    @admin_router.message(StateFilter(AdminStates.faq_add_answer), F.text)
    async def faq_add_answer(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(settings, user_id):
            return
        answer = (message.text or "").strip()
        if not answer:
            await message.answer("Ответ не может быть пустым.", parse_mode=None)
            return
        if answer.startswith("/"):
            await message.answer(_COMMAND_REJECT_HINT, parse_mode=None)
            return
        data = await state.get_data()
        key = str(data.get("faq_key", ""))
        storage.admin_set_faq(user_id, key, answer)
        await state.clear()
        await message.answer(
            _format_faq_saved_message(key, answer),
            reply_markup=_back_to_faq_kb(),
            parse_mode=None,
        )

    @admin_router.message(StateFilter(AdminStates.faq_edit), F.text)
    async def faq_edit_text(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(settings, user_id):
            return
        answer = (message.text or "").strip()
        if not answer:
            await message.answer("Ответ не может быть пустым.", parse_mode=None)
            return
        if answer.startswith("/"):
            await message.answer(_COMMAND_REJECT_HINT, parse_mode=None)
            return
        data = await state.get_data()
        key = str(data.get("faq_key", ""))
        old = str(data.get("faq_old", ""))
        storage.admin_set_faq(user_id, key, answer)
        await state.clear()
        await message.answer(
            _format_faq_saved_message(key, answer, old=old),
            reply_markup=_back_to_faq_kb(),
            parse_mode=None,
        )

    @admin_router.callback_query(F.data == "adm:esc")
    async def cb_esc_menu(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            _legacy_config_hint(),
            reply_markup=_legacy_redirect_kb(settings),
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data.regexp(r"^adm:esc:i:\d+$"))
    async def cb_esc_toggle(callback: CallbackQuery) -> None:
        if not callback.message or not callback.from_user or not callback.data:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        index = int(callback.data.rsplit(":", 1)[-1])
        items = storage.admin_list_escalation_rules()
        if index >= len(items):
            await callback.answer("Слово не найдено", show_alert=True)
            return
        keyword, active = items[index]
        storage.admin_set_escalation_keyword(callback.from_user.id, keyword, not active)
        items = storage.admin_list_escalation_rules()
        await callback.message.edit_reply_markup(reply_markup=_escalation_kb(items))
        status = "включено" if not active else "выключено"
        await callback.answer(f"«{keyword}» {status}")

    @admin_router.callback_query(F.data == "adm:esc:add")
    async def cb_esc_add(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.set_state(AdminStates.esc_add)
        await callback.message.edit_text(
            "Новый триггер эскалации\n\n"
            "Напишите слово или фразу. Если клиент напишет её — бот передаст менеджеру.\n"
            "Пример: директор",
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.message(StateFilter(AdminStates.esc_add), F.text)
    async def esc_add_keyword(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(settings, user_id):
            return
        keyword = (message.text or "").strip().lower()
        if not keyword or keyword.startswith("/"):
            await message.answer("Введите слово или фразу без команды. Отмена: /admin_cancel", parse_mode=None)
            return
        storage.admin_set_escalation_keyword(user_id, keyword, True)
        await state.clear()
        await message.answer(
            f"✅ Триггер «{keyword}» добавлен и включён.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="⚡ Эскалация", callback_data="adm:esc"),
                        InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu"),
                    ]
                ]
            ),
            parse_mode=None,
        )

    @admin_router.callback_query(F.data == "adm:fee")
    async def cb_fee_menu(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            _legacy_config_hint(),
            reply_markup=_legacy_redirect_kb(settings),
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.callback_query(F.data.regexp(r"^adm:fee:i:\d+$"))
    async def cb_fee_edit(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user or not callback.data:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        index = int(callback.data.rsplit(":", 1)[-1])
        items = storage.admin_list_service_fees()
        if index >= len(items):
            await callback.answer("Параметр не найден", show_alert=True)
            return
        code, value = items[index]
        await state.set_state(AdminStates.fee_edit)
        await state.update_data(fee_code=code, fee_old=value)
        if code == "assembly_percent":
            hint = f"Текущее значение: {value * 100:.0f}%\n\nВведите процент числом, например: 15"
        else:
            hint = f"Текущее значение: {value:,.0f} ₽\n\nВведите новое число, например: 15000".replace(
                ",", " "
            )
        await callback.message.edit_text(
            f"Параметр: {_fee_label(code)}\n\n{hint}",
            parse_mode=None,
        )
        await callback.answer()

    @admin_router.message(StateFilter(AdminStates.fee_edit), F.text)
    async def fee_edit_value(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0
        if not _is_admin(settings, user_id):
            return
        raw = (message.text or "").strip()
        if raw.startswith("/"):
            await message.answer(_COMMAND_REJECT_HINT, parse_mode=None)
            return
        data = await state.get_data()
        code = str(data.get("fee_code", ""))
        old = float(data.get("fee_old", 0))
        value, error = parse_fee_input(raw, code)
        if error:
            await message.answer(error, parse_mode=None)
            return
        assert value is not None
        storage.admin_set_service_fee(user_id, code, value)
        await state.clear()
        if code == "assembly_percent":
            old_text = f"{old * 100:.0f}%"
            new_text = f"{value * 100:.0f}%"
        else:
            old_text = f"{old:,.0f} ₽".replace(",", " ")
            new_text = f"{value:,.0f} ₽".replace(",", " ")
        await message.answer(
            f"✅ {_fee_label(code)} обновлён\n\nБыло: {old_text}\nСтало: {new_text}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="💰 Сборы", callback_data="adm:fee"),
                        InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu"),
                    ]
                ]
            ),
            parse_mode=None,
        )

    @admin_router.callback_query(F.data == "adm:sum")
    async def cb_summary(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            return
        if not _is_admin(settings, callback.from_user.id):
            await callback.answer("Нет доступа", show_alert=True)
            return
        await state.clear()
        if not hasattr(storage, "get_daily_summary"):
            await callback.message.edit_text(
                "📊 Сводка доступна только при подключённой базе данных.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu")]]
                ),
                parse_mode=None,
            )
            await callback.answer()
            return
        summary = storage.get_daily_summary()
        text = build_daily_report_text(summary)
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Меню", callback_data="adm:menu")]]
            ),
            parse_mode=None,
        )
        await callback.answer()
