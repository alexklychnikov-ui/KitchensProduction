from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable

from .faq_content import QA_CONTINUE_BRIDGE, format_friendly_faq_reply, stems_compatible, tokenize_words
from .pricing import (
    PRICE_INTENT_KEYWORDS,
    build_catalog_estimate,
    class_display_label,
    detect_length,
    sorted_product_classes,
)

FUNNEL_ABSORBED_KEYWORDS = frozenset({"замер", "замерщик"})

ORDER_INTENT = ("заказать", "хочу кухн", "оформить", "беру", "готов заказать", "подобрать", "конфигуратор")
MANAGER_INTENT = (
    "менеджер",
    "человек",
    "оператор",
    "опреатор",
    "позвоните",
    "перезвоните",
    "перезвон",
    "свяж",
    "связать",
    "связаться",
    "живой",
    "живого",
    "специалист",
)

MANAGER_PHONE_PROMPT = (
    "Хорошо, передам менеджеру. Оставьте номер телефона — он перезвонит вам.\n\n"
    "Формат: +7 9XX XXX XX XX (можно с именем: «Иван, +7 964 123 45 67»)"
)

WIZARD_STAGES = ("style", "length", "shape", "budget", "facade", "countertop", "hardware", "estimate", "phone", "done")

CATEGORY_BY_STAGE = {
    "style": "style",
    "facade": "facade",
    "countertop": "countertop",
    "hardware": "hardware",
}

STAGE_PROMPTS = {
    "style": "Шаг 1 из 8. Выберите стиль кухни:",
    "length": "Шаг 2 из 8. Напишите длину кухни по стене в метрах (например: 3.2 м):",
    "shape": "Шаг 3 из 8. Какая планировка?",
    "budget": "Шаг 4 из 8. Какой ориентир по бюджету? (класс комплектации из прайса)",
    "facade": "Шаг 5 из 8. Выберите фасады:",
    "countertop": "Шаг 6 из 8. Выберите столешницу:",
    "hardware": "Шаг 7 из 8. Выберите фурнитуру:",
    "estimate": "Шаг 8 из 8. Ориентир по вашей комплектации:",
    "phone": "Оставьте номер телефона — менеджер свяжется и согласует замер:",
}

SHAPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("straight", "Прямая"),
    ("corner", "Угловая"),
    ("u_shape", "П-образная"),
    ("g_shape", "Г-образная"),
)

SHAPE_LABELS = {code: label for code, label in SHAPE_OPTIONS}

STAGE_ORDER: tuple[tuple[str, str, int], ...] = (
    ("style", "стиль кухни", 1),
    ("length", "длину по стене", 2),
    ("shape", "планировку", 3),
    ("budget", "ориентир по бюджету", 4),
    ("facade", "фасады", 5),
    ("countertop", "столешницу", 6),
    ("hardware", "фурнитуру", 7),
    ("estimate", "итоговый расчёт", 8),
    ("phone", "контакт для замера", 9),
)

STAGE_ACTION_HINTS: dict[str, str] = {
    "style": "Листайте фото ◀️ ▶️ и нажмите «Выбрать» под понравившимся стилем.",
    "length": "Напишите длину кухни числом, например: 3 или 3.5 (можно с «м»).",
    "shape": "Нажмите кнопку с нужной планировкой ниже.",
    "budget": "Выберите класс — цены из вкладки Прайс → Классы (₽/пог.м).",
    "facade": "Листайте варианты фасадов и нажмите «Выбрать» — цена за погонный метр в подписи.",
    "countertop": "Листайте столешницы ◀️ ▶️ и выберите подходящую по цене и виду.",
    "hardware": "Выберите фурнитуру — от неё зависит ресурс и плавность хода ящиков.",
    "estimate": "Если ориентир подходит — нажмите «Записать на замер».",
    "phone": "Напишите телефон в формате +7 9XX XXX XX XX — передадим менеджеру.",
}

QUESTION_HINTS = (
    "?",
    "как ",
    "что ",
    "сколько",
    "почему",
    "можно",
    "это ",
    "а ",
    "где ",
    "когда",
    "весь",
    "все ",
    "есть ли",
    "какой",
    "какая",
    "какие",
    "расскаж",
    "объясн",
    "подскаж",
)

TOPIC_TO_STAGE: dict[str, str] = {
    "стил": "style",
    "фасад": "facade",
    "эмаль": "facade",
    "мдф": "facade",
    "шпон": "facade",
    "столешн": "countertop",
    "кварц": "countertop",
    "акрил": "countertop",
    "фурнит": "hardware",
    "длин": "length",
    "планир": "shape",
    "погон": "length",
    "замер": "phone",
    "бюджет": "budget",
    "класс": "budget",
    "ценов": "budget",
}

ALTERNATIVE_QUESTION_MARKERS: tuple[str, ...] = (
    "а нет",
    "нет ли",
    "не нет",
    "а есть",
    "есть ли",
    "можно ли",
    "другой",
    "другая",
    "другие",
    "другое",
    "ещё",
    "еще",
    "иной",
    "иная",
    "под ",
    "похож",
    "аналог",
    "только так",
    "больше нет",
    "ничего кроме",
)


@dataclass
class FunnelState:
    stage: str = "idle"
    style_code: str | None = None
    style_title: str | None = None
    facade_code: str | None = None
    facade_title: str | None = None
    countertop_code: str | None = None
    countertop_title: str | None = None
    hardware_code: str | None = None
    hardware_title: str | None = None
    length_m: float | None = None
    shape: str | None = None
    kitchen_class: str | None = None
    phone: str | None = None
    name: str | None = None
    estimate_total: int | None = None
    order_id: int | None = None
    pending_manager: bool = False
    carousel_index: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FunnelState:
        if not data:
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_active(self) -> bool:
        return self.stage in WIZARD_STAGES and self.stage != "done"


@dataclass
class FunnelResult:
    handled: bool = True
    text: str = ""
    keyboard: list[list[tuple[str, str]]] | None = None
    photo_file_id: str | None = None
    photo_url: str | None = None
    photo_path: str | None = None
    catalog_item_id: int | None = None
    carousel_category: str | None = None
    carousel_index: int = 0
    carousel_items: list[dict[str, Any]] | None = None
    carousel_header: str = ""
    should_escalate: bool = False
    escalation_summary: str = ""
    progress_made: bool = False
    create_order: bool = False
    order_payload: dict[str, Any] | None = None
    escalation_reasons: list[str] | None = None


def filter_escalation_keywords(keywords: list[str], text: str) -> list[str]:
    normalized = text.lower()
    if any(token in normalized for token in ("замер", "замерщик", "записать", "запишите")):
        return [kw for kw in keywords if kw not in FUNNEL_ABSORBED_KEYWORDS]
    return keywords


def wants_to_start_order(text: str) -> bool:
    normalized = text.lower().strip()
    return any(token in normalized for token in ORDER_INTENT)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _detect_phone(text: str) -> str | None:
    match = re.search(r"(?:\+7|8)[\s\-()]*(?:\d[\s\-()]*){10}", text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return f"+{digits}"
    return None


def _detect_name(text: str) -> str | None:
    patterns = [
        r"(?:меня зовут|я|это)\s+([А-ЯЁA-Z][а-яёa-z]{1,20})",
        r"имя[:\s]+([А-ЯЁA-Z][а-яёa-z]{1,20})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.strip())
        if match:
            return match.group(1)
    return None


def _format_money(value: float | int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _pick_callback(category: str, code: str) -> str:
    return f"fn:pick:{category}:{code}"


def _nav_callback(category: str, index: int) -> str:
    return f"fn:nav:{category}:{index}"


PER_M_CATEGORIES = frozenset({"facade", "countertop"})


def format_catalog_price_line(item: dict[str, Any]) -> str:
    price = item.get("price_from")
    if price is not None:
        value = float(price)
        if value > 0:
            money = f"{_format_money(value)} ₽"
            category = str(item.get("category") or "")
            if category in PER_M_CATEGORIES:
                return f"💰 от {money}/пог.м"
            return f"💰 от {money}"
    category = str(item.get("category") or "")
    if category == "style":
        return "💰 Цена зависит от фасадов и комплектации"
    if category == "hardware":
        return "💰 Учитывается в итоговом расчёте"
    return ""


def build_carousel_caption(item: dict[str, Any], *, index: int, total: int, header: str) -> str:
    lines = [line for line in header.strip().split("\n") if line.strip()]
    lines.append(f"📷 {index + 1} из {total}")
    lines.append(str(item.get("title") or ""))
    desc = str(item.get("description") or "").strip()
    if desc:
        lines.append(desc)
    price_line = format_catalog_price_line(item)
    if price_line:
        lines.append(price_line)
    return "\n".join(lines)


def carousel_keyboard(category: str, items: list[dict[str, Any]], index: int) -> list[list[tuple[str, str]]]:
    total = len(items)
    safe_index = max(0, min(index, total - 1))
    item = items[safe_index]
    nav_row: list[tuple[str, str]] = []
    if safe_index > 0:
        nav_row.append(("◀️", _nav_callback(category, safe_index - 1)))
    price_hint = ""
    price = item.get("price_from")
    if price is not None and float(price) > 0:
        price_hint = f" · {_format_money(price)} ₽"
    nav_row.append((f"Выбрать{price_hint}", _pick_callback(category, str(item["code"]))))
    if safe_index < total - 1:
        nav_row.append(("▶️", _nav_callback(category, safe_index + 1)))
    return [nav_row]


def build_carousel_result(
    category: str,
    items: list[dict[str, Any]],
    index: int,
    header: str,
) -> FunnelResult:
    if not items:
        return FunnelResult(
            text=f"{header}\n\nПока нет позиций в каталоге.",
            progress_made=True,
        )
    safe_index = max(0, min(index, len(items) - 1))
    return FunnelResult(
        carousel_category=category,
        carousel_index=safe_index,
        carousel_items=items,
        carousel_header=header,
        progress_made=True,
    )


def carousel_nav_result(
    category: str,
    index: int,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    header: str,
) -> FunnelResult:
    items = catalog_lookup(category)
    return build_carousel_result(category, items, index, header)


def build_carousel_header(state: FunnelState, category: str) -> str:
    if category == "style":
        return STAGE_PROMPTS["style"]
    if category == "facade":
        prefix = ""
        if state.shape:
            prefix = f"Планировка: {state.shape} ✓\n"
        if state.kitchen_class:
            label = class_display_label(state.kitchen_class)
            prefix += f"Класс: {label} ✓\n"
        return f"{prefix}\n{STAGE_PROMPTS['facade']}".strip()
    if category == "countertop" and state.facade_title:
        return f"Фасады: {state.facade_title} ✓\n\n{STAGE_PROMPTS['countertop']}"
    if category == "hardware" and state.countertop_title:
        return f"Столешница: {state.countertop_title} ✓\n\n{STAGE_PROMPTS['hardware']}"
    stage = next((s for s, c in CATEGORY_BY_STAGE.items() if c == category), None)
    return STAGE_PROMPTS.get(stage or category, "")


def _shape_callback(code: str) -> str:
    return f"fn:pick:shape:{code}"


def _shape_keyboard() -> list[list[tuple[str, str]]]:
    return [[(label, _shape_callback(code))] for code, label in SHAPE_OPTIONS]


def _budget_callback(code: str) -> str:
    return f"fn:pick:budget:{code}"


def _budget_keyboard(pricing_reference: dict[str, Any]) -> list[list[tuple[str, str]]]:
    product_classes = pricing_reference.get("product_classes", {})
    rows: list[list[tuple[str, str]]] = []
    for code, price in sorted_product_classes(product_classes):
        label = class_display_label(code)
        rows.append([(f"{label} — от {_format_money(price)} ₽/пог.м", _budget_callback(code))])
    return rows or [[("Стандарт", _budget_callback("стандарт"))]]


def _estimate_keyboard() -> list[list[tuple[str, str]]]:
    return [[("Записать на замер", "fn:confirm:estimate")]]


def _start_keyboard() -> list[list[tuple[str, str]]]:
    return [[("Подобрать кухню", "fn:start")]]


def _media_from_item(
    item: dict[str, Any],
    *,
    public_base_url: str | None,
    uploads_dir: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    if item.get("telegram_file_id"):
        return str(item["telegram_file_id"]), None, None
    image_path = item.get("image_path") or item.get("image_thumb_path")
    if not image_path:
        return None, None, None
    if str(image_path).startswith("/catalog/media/") and public_base_url:
        return None, f"{public_base_url.rstrip('/')}{image_path}", None
    if uploads_dir and str(image_path).startswith("/uploads/"):
        from pathlib import Path

        rel = str(image_path).removeprefix("/uploads/").removeprefix("uploads/")
        local = Path(uploads_dir) / rel
        if local.exists():
            return None, None, str(local)
    if public_base_url and str(image_path).startswith("/"):
        return None, f"{public_base_url.rstrip('/')}{image_path}", None
    return None, None, None


def _step_result_for_stage(
    stage: str,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    prefix: str = "",
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
    pricing_reference: dict[str, Any] | None = None,
) -> FunnelResult:
    text = f"{prefix}{STAGE_PROMPTS[stage]}" if prefix else STAGE_PROMPTS[stage]
    keyboard: list[list[tuple[str, str]]] | None = None

    if stage == "shape":
        keyboard = _shape_keyboard()
    elif stage == "budget":
        keyboard = _budget_keyboard(pricing_reference or {})
    elif stage == "estimate":
        keyboard = _estimate_keyboard()
    elif stage in CATEGORY_BY_STAGE:
        category = CATEGORY_BY_STAGE[stage]
        items = catalog_lookup(category)
        return build_carousel_result(category, items, 0, text)

    return FunnelResult(
        text=text,
        keyboard=keyboard,
        progress_made=True,
    )


def start_wizard(
    state: FunnelState,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> tuple[FunnelState, FunnelResult]:
    state.stage = "style"
    state.carousel_index = 0
    result = _step_result_for_stage(
        "style",
        catalog_lookup=catalog_lookup,
        public_base_url=public_base_url,
        uploads_dir=uploads_dir,
    )
    return state, result


def apply_catalog_pick(
    state: FunnelState,
    category: str,
    code: str,
    item: dict[str, Any],
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    pricing_reference: dict[str, Any],
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> tuple[FunnelState, FunnelResult]:
    title = str(item["title"])
    state.carousel_index = 0
    if category == "style":
        state.style_code = code
        state.style_title = title
        state.stage = "length"
        return state, FunnelResult(
            text=f"Стиль: {title} ✓\n\n{STAGE_PROMPTS['length']}",
            progress_made=True,
        )

    if category == "facade":
        state.facade_code = code
        state.facade_title = title
        state.stage = "countertop"
        result = _step_result_for_stage(
            "countertop",
            catalog_lookup=catalog_lookup,
            prefix=f"Фасады: {title} ✓\n\n",
            public_base_url=public_base_url,
            uploads_dir=uploads_dir,
        )
        return state, result

    if category == "countertop":
        state.countertop_code = code
        state.countertop_title = title
        state.stage = "hardware"
        result = _step_result_for_stage(
            "hardware",
            catalog_lookup=catalog_lookup,
            prefix=f"Столешница: {title} ✓\n\n",
            public_base_url=public_base_url,
            uploads_dir=uploads_dir,
        )
        return state, result

    if category == "hardware":
        state.hardware_code = code
        state.hardware_title = title
        state.stage = "estimate"
        estimate = build_catalog_estimate(
            length_m=state.length_m or 4.0,
            facade_price_pm=_facade_price(state, catalog_lookup),
            countertop_price_pm=_countertop_price(state, catalog_lookup),
            style_title=state.style_title,
            facade_title=state.facade_title,
            countertop_title=state.countertop_title,
            hardware_title=title,
            shape=state.shape,
            kitchen_class=state.kitchen_class,
            hardware_price_pm=_hardware_price(state, catalog_lookup),
            pricing_reference=pricing_reference,
        )
        state.estimate_total = int(estimate.total)
        return state, FunnelResult(
            text=f"Фурнитура: {title} ✓\n\n{estimate.text}\n\nЕсли подходит — запишем на бесплатный замер.",
            keyboard=_estimate_keyboard(),
            progress_made=True,
        )

    return state, FunnelResult(handled=False, text="")


def _facade_price(state: FunnelState, catalog_lookup: Callable[[str], list[dict[str, Any]]]) -> float:
    if not state.facade_code:
        return 38000.0
    item = next((i for i in catalog_lookup("facade") if i["code"] == state.facade_code), None)
    return float(item["price_from"]) if item and item.get("price_from") is not None else 38000.0


def _countertop_price(state: FunnelState, catalog_lookup: Callable[[str], list[dict[str, Any]]]) -> float:
    if not state.countertop_code:
        return 14000.0
    item = next((i for i in catalog_lookup("countertop") if i["code"] == state.countertop_code), None)
    return float(item["price_from"]) if item and item.get("price_from") is not None else 14000.0


def _hardware_price(state: FunnelState, catalog_lookup: Callable[[str], list[dict[str, Any]]]) -> float:
    if not state.hardware_code:
        return 0.0
    item = next((i for i in catalog_lookup("hardware") if i["code"] == state.hardware_code), None)
    if item and item.get("price_from") is not None:
        return max(0.0, float(item["price_from"]))
    return 0.0


def apply_shape_pick(
    state: FunnelState,
    shape_code: str,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    pricing_reference: dict[str, Any] | None = None,
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> tuple[FunnelState, FunnelResult]:
    label = SHAPE_LABELS.get(shape_code, shape_code)
    state.shape = label
    state.stage = "budget"
    result = _step_result_for_stage(
        "budget",
        catalog_lookup=catalog_lookup,
        prefix=f"Планировка: {label} ✓\n\n",
        public_base_url=public_base_url,
        uploads_dir=uploads_dir,
        pricing_reference=pricing_reference or {},
    )
    return state, result


def apply_budget_pick(
    state: FunnelState,
    class_code: str,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    pricing_reference: dict[str, Any],
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> tuple[FunnelState, FunnelResult]:
    product_classes = pricing_reference.get("product_classes", {})
    if class_code not in product_classes:
        class_code = "стандарт"
    state.kitchen_class = class_code
    state.stage = "facade"
    label = class_display_label(class_code)
    price = float(product_classes[class_code])
    prefix = f"Планировка: {state.shape} ✓\nКласс: {label} (от {_format_money(price)} ₽/пог.м) ✓\n\n"
    result = _step_result_for_stage(
        "facade",
        catalog_lookup=catalog_lookup,
        prefix=prefix,
        public_base_url=public_base_url,
        uploads_dir=uploads_dir,
        pricing_reference=pricing_reference,
    )
    return state, result


def confirm_estimate(state: FunnelState) -> tuple[FunnelState, FunnelResult]:
    state.stage = "phone"
    return state, FunnelResult(
        text=(
            "Отлично! Оставьте номер телефона — менеджер перезвонит "
            "и запишет на бесплатный замер с образцами материалов."
        ),
        progress_made=True,
    )


def _build_order_payload(state: FunnelState) -> dict[str, Any]:
    return {
        "style_code": state.style_code,
        "facade_code": state.facade_code,
        "countertop_code": state.countertop_code,
        "hardware_code": state.hardware_code,
        "length_m": state.length_m,
        "shape": state.shape,
        "phone": state.phone,
        "name": state.name,
        "estimate_total": state.estimate_total,
        "style_title": state.style_title,
        "facade_title": state.facade_title,
        "countertop_title": state.countertop_title,
        "hardware_title": state.hardware_title,
        "kitchen_class": state.kitchen_class,
    }


def _has_funnel_progress(state: FunnelState) -> bool:
    return bool(state.style_code or state.estimate_total is not None or state.facade_code)


def request_manager_contact(state: FunnelState) -> tuple[FunnelState, FunnelResult]:
    if state.phone:
        state.stage = "done"
        state.pending_manager = False
        summary = _build_escalation_summary(state, header="Запрос связи с менеджером")
        create = _has_funnel_progress(state)
        payload = _build_order_payload(state) if create else None
        return state, FunnelResult(
            text="Передал запрос менеджеру. Специалист свяжется с вами в ближайшее время.",
            should_escalate=True,
            escalation_summary=summary,
            create_order=create,
            order_payload=payload,
            escalation_reasons=["manager_requested"],
            progress_made=True,
        )
    state.stage = "phone"
    state.pending_manager = True
    return state, FunnelResult(text=MANAGER_PHONE_PROMPT, progress_made=True)


def _build_escalation_summary(
    state: FunnelState,
    order_id: int | None = None,
    *,
    header: str = "Новый заказ кухни",
) -> str:
    lines = [header]
    if order_id is not None:
        lines.append(f"Заказ №{order_id}")
    if state.name:
        lines.append(f"Имя: {state.name}")
    if state.phone:
        lines.append(f"Телефон: {state.phone}")
    if state.style_title:
        lines.append(f"Стиль: {state.style_title}")
    if state.length_m is not None:
        lines.append(f"Длина: {state.length_m:.1f} м")
    if state.shape:
        lines.append(f"Планировка: {state.shape}")
    if state.kitchen_class:
        lines.append(f"Класс: {class_display_label(state.kitchen_class)}")
    if state.facade_title:
        lines.append(f"Фасады: {state.facade_title}")
    if state.countertop_title:
        lines.append(f"Столешница: {state.countertop_title}")
    if state.hardware_title:
        lines.append(f"Фурнитура: {state.hardware_title}")
    if state.estimate_total is not None:
        lines.append(f"Ориентир: {_format_money(state.estimate_total)} ₽")
    return "\n".join(lines)


def _looks_like_question(text: str) -> bool:
    normalized = text.lower().strip()
    if "?" in normalized:
        return True
    return any(marker in normalized for marker in QUESTION_HINTS)


def _stage_meta(stage: str) -> tuple[str, str, int]:
    for code, title, step in STAGE_ORDER:
        if code == stage:
            return code, title, step
    return stage, stage, 0


def _progress_summary(state: FunnelState) -> str:
    parts: list[str] = []
    if state.style_title:
        parts.append(f"стиль: {state.style_title}")
    if state.length_m is not None:
        parts.append(f"длина: {state.length_m:.1f} м")
    if state.shape:
        parts.append(f"планировка: {state.shape}")
    if state.kitchen_class:
        parts.append(f"класс: {class_display_label(state.kitchen_class)}")
    if state.facade_title:
        parts.append(f"фасады: {state.facade_title}")
    if state.countertop_title:
        parts.append(f"столешница: {state.countertop_title}")
    if state.hardware_title:
        parts.append(f"фурнитура: {state.hardware_title}")
    return ", ".join(parts) if parts else "пока ничего не выбрано"


def _asks_about_catalog_alternatives(text: str) -> bool:
    normalized = text.lower().strip()
    return any(marker in normalized for marker in ALTERNATIVE_QUESTION_MARKERS)


def _topic_in_text(topic: str, text: str) -> bool:
    normalized = text.lower().strip()
    if topic in normalized:
        return True
    return any(stems_compatible(topic, word) for word in tokenize_words(normalized))


def _earlier_catalog_stage_from_question(text: str, state: FunnelState) -> str | None:
    normalized = text.lower().strip()
    _, _, current_step = _stage_meta(state.stage)
    for topic, target_stage in TOPIC_TO_STAGE.items():
        if not _topic_in_text(topic, normalized):
            continue
        if target_stage not in CATEGORY_BY_STAGE:
            continue
        _, _, target_step = _stage_meta(target_stage)
        if target_step < current_step:
            return target_stage
    return None


def _rewind_to_catalog_step(state: FunnelState, target_stage: str) -> None:
    if target_stage == "style":
        state.style_code = None
        state.style_title = None
        state.facade_code = None
        state.facade_title = None
        state.countertop_code = None
        state.countertop_title = None
        state.hardware_code = None
        state.hardware_title = None
        state.estimate_total = None
    elif target_stage == "facade":
        state.facade_code = None
        state.facade_title = None
        state.countertop_code = None
        state.countertop_title = None
        state.hardware_code = None
        state.hardware_title = None
        state.estimate_total = None
    elif target_stage == "countertop":
        state.countertop_code = None
        state.countertop_title = None
        state.hardware_code = None
        state.hardware_title = None
        state.estimate_total = None
    elif target_stage == "hardware":
        state.hardware_code = None
        state.hardware_title = None
        state.estimate_total = None
    state.stage = target_stage
    state.carousel_index = 0


def _mentions_option_outside_catalog(text: str, items: list[dict[str, Any]]) -> bool:
    if not _looks_like_question(text):
        return False
    catalog_words: set[str] = set()
    for item in items:
        blob = f"{item.get('title', '')} {item.get('description', '')}"
        catalog_words.update(tokenize_words(str(blob)))
    for word in tokenize_words(text):
        if len(word) < 4:
            continue
        if word in catalog_words:
            continue
        if any(stems_compatible(word, catalog_word) for catalog_word in catalog_words):
            continue
        return True
    return False


def _build_step_catalog_limit_reply(
    state: FunnelState,
    items: list[dict[str, Any]],
) -> str:
    _, stage_title, _ = _stage_meta(state.stage)
    titles = [str(item.get("title") or "").strip() for item in items if item.get("title")]
    if not titles:
        return f"К сожалению, на шаге «{stage_title}» пока нет позиций в каталоге."
    bullets = "\n".join(f"• {title}" for title in titles)
    return (
        f"К сожалению, на этом шаге можем предложить только {len(titles)} "
        f"{_variants_word(len(titles))} — листайте ◀️ ▶️ и нажмите «Выбрать»:\n"
        f"{bullets}"
    )


def _wrong_step_hint(state: FunnelState, text: str) -> str | None:
    normalized = text.lower()
    _, current_title, current_step = _stage_meta(state.stage)
    for topic, target_stage in TOPIC_TO_STAGE.items():
        if not _topic_in_text(topic, normalized):
            continue
        if target_stage == state.stage:
            continue
        for code, title, step in STAGE_ORDER:
            if code == target_stage:
                if step < current_step:
                    return (
                        f"«{title.capitalize()}» уже на шаге {step}. "
                        f"Сейчас шаг {current_step} — {current_title}."
                    )
                return (
                    f"«{title.capitalize()}» будет на шаге {step}. "
                    f"Сейчас шаг {current_step} — {current_title}, давайте по порядку 🙂"
                )
    if any(word in normalized for word in ("весь", "все", "полный", "каталог", "вариант")):
        if state.stage in CATEGORY_BY_STAGE:
            return None
    return None


def _step_context_lines(state: FunnelState) -> list[str]:
    lines: list[str] = []
    if state.style_title and state.stage != "style":
        lines.append(f"Стиль: {state.style_title} ✓")
    if state.length_m is not None and state.stage not in ("style", "length"):
        lines.append(f"Длина: {state.length_m:.1f} м ✓")
    if state.shape and state.stage not in ("style", "length", "shape"):
        lines.append(f"Планировка: {state.shape} ✓")
    if state.kitchen_class and state.stage not in ("style", "length", "shape", "budget"):
        lines.append(f"Класс: {class_display_label(state.kitchen_class)} ✓")
    if state.facade_title and state.stage in ("countertop", "hardware", "estimate"):
        lines.append(f"Фасады: {state.facade_title} ✓")
    if state.countertop_title and state.stage in ("hardware", "estimate"):
        lines.append(f"Столешница: {state.countertop_title} ✓")
    if state.hardware_title and state.stage == "estimate":
        lines.append(f"Фурнитура: {state.hardware_title} ✓")
    return lines


def _resume_wizard_step(
    state: FunnelState,
    content_lines: list[str],
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    pricing_reference: dict[str, Any],
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> FunnelResult:
    blocks = [block for block in content_lines if block.strip()]
    blocks.append(QA_CONTINUE_BRIDGE)
    context = _step_context_lines(state)
    if context:
        blocks.append("\n".join(context))

    step_prompt = STAGE_PROMPTS.get(state.stage, "")
    action = STAGE_ACTION_HINTS.get(state.stage, "")
    if step_prompt:
        blocks.append(step_prompt)
    if action and state.stage != "length":
        blocks.append(action)

    body = "\n\n".join(blocks)

    if state.stage in CATEGORY_BY_STAGE:
        category = CATEGORY_BY_STAGE[state.stage]
        items = catalog_lookup(category)
        safe_index = max(0, min(state.carousel_index, len(items) - 1)) if items else 0
        result = build_carousel_result(category, items, safe_index, body)
        result.text = body
        result.progress_made = False
        return result

    keyboard: list[list[tuple[str, str]]] | None = None
    if state.stage == "shape":
        keyboard = _shape_keyboard()
    elif state.stage == "budget":
        keyboard = _budget_keyboard(pricing_reference)
    elif state.stage == "estimate":
        keyboard = _estimate_keyboard()

    return FunnelResult(text=body, keyboard=keyboard, handled=True, progress_made=False)


def answer_wizard_question(
    text: str,
    state: FunnelState,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    pricing_reference: dict[str, Any],
    faq_lookup: Callable[[str], str | None],
    faq_match_lookup: Callable[[str], tuple[str, str] | None] | None = None,
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> tuple[FunnelState, FunnelResult]:
    normalized = text.lower().strip()
    if _contains_any(normalized, MANAGER_INTENT):
        return request_manager_contact(state)

    _, current_title, current_step = _stage_meta(state.stage)
    lines: list[str] = []
    rewound = False

    earlier_stage = _earlier_catalog_stage_from_question(text, state)
    if earlier_stage:
        _rewind_to_catalog_step(state, earlier_stage)
        rewound = True
        _, current_title, current_step = _stage_meta(state.stage)
        lines.append(
            "Выбор фиксируется только кнопкой «Выбрать». "
            f"Вернул вас к шагу {current_step} — {current_title}."
        )

    wrong_step = None if rewound else _wrong_step_hint(state, text)
    if wrong_step:
        lines.append(wrong_step)

    if any(word in normalized for word in ("весь", "все", "полный", "сколько вариант", "это все")):
        if state.stage in CATEGORY_BY_STAGE:
            category = CATEGORY_BY_STAGE[state.stage]
            count = len(catalog_lookup(category))
            lines.append(
                f"На этом шаге {count} {_variants_word(count)} в каталоге. "
                "Можно листать ◀️ ▶️ — это весь текущий выбор."
            )

    faq_match = faq_match_lookup(text) if faq_match_lookup else None
    if not faq_match:
        answer = faq_lookup(text)
        if answer:
            faq_match = ("", answer)
    if faq_match:
        faq_key, faq = faq_match
        lines.append(format_friendly_faq_reply(faq, faq_key=faq_key or None))

    if any(key in normalized for key in PRICE_INTENT_KEYWORDS):
        if state.stage == "estimate" and state.estimate_total is not None:
            lines.append(f"Ориентир по вашей комплектации: {_format_money(state.estimate_total)} ₽.")
        elif state.length_m and state.facade_code:
            lines.append(
                "Точная цена зависит от выбранных материалов. "
                "После всех шагов покажем ориентир — или задайте длину и материалы по шагам."
            )
        else:
            lines.append(
                "Цена складывается из длины, фасадов, столешницы и фурнитуры. "
                "Пройдём подбор — в конце будет ориентир в рублях."
            )

    if state.style_title and "стил" in normalized and state.stage != "style":
        lines.append(f"Выбранный стиль: {state.style_title}.")

    progress = _progress_summary(state)
    if progress != "пока ничего не выбрано" and any(
        word in normalized for word in ("где", "что выбран", "на каком", "этап", "шаг")
    ):
        lines.append(f"Уже выбрано: {progress}.")

    catalog_limit_added = False
    if state.stage in CATEGORY_BY_STAGE:
        category = CATEGORY_BY_STAGE[state.stage]
        items = catalog_lookup(category)
        if items and (
            rewound
            or _asks_about_catalog_alternatives(text)
            or _mentions_option_outside_catalog(text, items)
        ):
            lines.append(_build_step_catalog_limit_reply(state, items))
            catalog_limit_added = True

    if not lines:
        if _looks_like_question(text):
            lines.append(
                f"Хороший вопрос. Сейчас мы на шаге {current_step} из 8 — {current_title}."
            )
        else:
            lines.append(f"Давайте продолжим подбор — шаг {current_step}: {current_title}.")

    result = _resume_wizard_step(
        state,
        lines,
        catalog_lookup=catalog_lookup,
        pricing_reference=pricing_reference,
        public_base_url=public_base_url,
        uploads_dir=uploads_dir,
    )
    if rewound:
        result.progress_made = True
    return state, result


def _variants_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "вариант"
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return "варианта"
    return "вариантов"


def process_wizard_text(
    text: str,
    state: FunnelState,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    pricing_reference: dict[str, Any],
    faq_lookup: Callable[[str], str | None] | None = None,
    faq_match_lookup: Callable[[str], tuple[str, str] | None] | None = None,
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> tuple[FunnelState, FunnelResult]:
    normalized = text.lower().strip()
    lookup_faq = faq_lookup or (lambda _t: None)
    if _contains_any(normalized, MANAGER_INTENT):
        return request_manager_contact(state)

    faq_hit = lookup_faq(text)
    length_value = detect_length(text, bare_number=True) if state.stage == "length" else None
    if faq_hit and length_value is None:
        return answer_wizard_question(
            text,
            state,
            catalog_lookup=catalog_lookup,
            pricing_reference=pricing_reference,
            faq_lookup=lookup_faq,
            faq_match_lookup=faq_match_lookup,
            public_base_url=public_base_url,
            uploads_dir=uploads_dir,
        )

    if state.stage == "length":
        length = length_value
        if length is not None:
            state.length_m = length
            state.stage = "shape"
            result = _step_result_for_stage(
                "shape",
                catalog_lookup=catalog_lookup,
                prefix=f"Длина: {length:.1f} м ✓\n\n",
                public_base_url=public_base_url,
                uploads_dir=uploads_dir,
            )
            return state, result
        if _looks_like_question(text) or lookup_faq(text) or any(k in normalized for k in PRICE_INTENT_KEYWORDS):
            return answer_wizard_question(
                text,
                state,
                catalog_lookup=catalog_lookup,
                pricing_reference=pricing_reference,
                faq_lookup=lookup_faq,
            faq_match_lookup=faq_match_lookup,
                public_base_url=public_base_url,
                uploads_dir=uploads_dir,
            )
        return state, FunnelResult(
            text="Не понял длину. Напишите число: 3 или 3.5 (можно с «м»)",
        )

    if state.stage == "phone":
        if _looks_like_question(text) or lookup_faq(text):
            return answer_wizard_question(
                text,
                state,
                catalog_lookup=catalog_lookup,
                pricing_reference=pricing_reference,
                faq_lookup=lookup_faq,
            faq_match_lookup=faq_match_lookup,
                public_base_url=public_base_url,
                uploads_dir=uploads_dir,
            )
        phone = _detect_phone(text)
        name = _detect_name(text)
        if name:
            state.name = name
        if not phone:
            prompt = (
                "Нужен номер в формате +7 9XX XXX XX XX. Можно с именем: «Иван, +7 964 123 45 67»"
            )
            if state.pending_manager:
                prompt = (
                    "Чтобы менеджер мог перезвонить, нужен телефон.\n\n"
                    "Формат: +7 9XX XXX XX XX (можно с именем)."
                )
            return state, FunnelResult(text=prompt)
        state.phone = phone
        was_manager = state.pending_manager
        state.pending_manager = False
        state.stage = "done"
        payload = _build_order_payload(state)
        if was_manager:
            summary = _build_escalation_summary(state, header="Запрос связи с менеджером")
            create = _has_funnel_progress(state)
            return state, FunnelResult(
                text="Спасибо! Менеджер перезвонит вам в ближайшее время.",
                should_escalate=True,
                escalation_summary=summary,
                create_order=create,
                order_payload=payload if create else None,
                escalation_reasons=["manager_requested"],
                progress_made=True,
            )
        summary = _build_escalation_summary(state)
        return state, FunnelResult(
            text=(
                "Супер, заявка принята! 📐\n"
                "Менеджер свяжется с вами и согласует удобное время замера."
            ),
            should_escalate=True,
            escalation_summary=summary,
            create_order=True,
            order_payload=payload,
            escalation_reasons=["order_created"],
            progress_made=True,
        )

    return answer_wizard_question(
        text,
        state,
        catalog_lookup=catalog_lookup,
        pricing_reference=pricing_reference,
        faq_lookup=lookup_faq,
        faq_match_lookup=faq_match_lookup,
        public_base_url=public_base_url,
        uploads_dir=uploads_dir,
    )


def process_idle_message(
    text: str,
    state: FunnelState,
    *,
    catalog_lookup: Callable[[str], list[dict[str, Any]]],
    public_base_url: str | None = None,
    uploads_dir: str | None = None,
) -> tuple[FunnelState, FunnelResult] | None:
    if wants_to_start_order(text):
        return start_wizard(
            state,
            catalog_lookup=catalog_lookup,
            public_base_url=public_base_url,
            uploads_dir=uploads_dir,
        )
    return None


def idle_offer_text() -> str:
    return (
        "Могу провести по шагам: стиль → длина → планировка → бюджет → "
        "фасады → столешница → фурнитура → ориентир и замер."
    )


def idle_offer_keyboard() -> list[list[tuple[str, str]]]:
    return _start_keyboard()
