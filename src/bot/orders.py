from __future__ import annotations

from datetime import datetime
from typing import Any

from .pricing import class_display_label


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _fmt_dt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)[:16]


def format_order_short(order: dict[str, Any]) -> str:
    oid = order.get("id", "?")
    phone = order.get("phone") or "—"
    total = _fmt_money(order.get("estimate_total"))
    created = _fmt_dt(order.get("created_at"))
    return f"#{oid} · {phone} · {total} ₽ · {created}"


def format_order_detail(order: dict[str, Any], dialogs: list[dict[str, Any]] | None = None) -> str:
    lines = [
        f"Заявка №{order.get('id', '?')}",
        f"Статус: {order.get('status', 'new')}",
        f"Дата: {_fmt_dt(order.get('created_at'))}",
    ]
    if order.get("user_id"):
        user_line = f"Клиент: {order.get('full_name') or '—'}"
        if order.get("username"):
            user_line += f" ({order['username']})"
        user_line += f" · id {order['user_id']}"
        lines.append(user_line)
    if order.get("phone"):
        lines.append(f"Телефон: {order['phone']}")
    if order.get("name"):
        lines.append(f"Имя: {order['name']}")
    if order.get("style_title") or order.get("style_code"):
        lines.append(f"Стиль: {order.get('style_title') or order.get('style_code')}")
    if order.get("length_m") is not None:
        lines.append(f"Длина: {float(order['length_m']):.1f} м")
    if order.get("shape"):
        lines.append(f"Планировка: {order['shape']}")
    kitchen_class = order.get("kitchen_class")
    if kitchen_class:
        lines.append(f"Класс: {class_display_label(str(kitchen_class))}")
    if order.get("facade_title") or order.get("facade_code"):
        lines.append(f"Фасады: {order.get('facade_title') or order.get('facade_code')}")
    if order.get("countertop_title") or order.get("countertop_code"):
        lines.append(f"Столешница: {order.get('countertop_title') or order.get('countertop_code')}")
    if order.get("hardware_title") or order.get("hardware_code"):
        lines.append(f"Фурнитура: {order.get('hardware_title') or order.get('hardware_code')}")
    if order.get("estimate_total") is not None:
        lines.append(f"Ориентир: {_fmt_money(order['estimate_total'])} ₽")

    if dialogs:
        lines.append("\nДиалог:")
        for item in dialogs[-12:]:
            text = str(item.get("text", "")).replace("\n", " ")
            if len(text) > 120:
                text = text[:119] + "…"
            lines.append(f"• [{item.get('source', 'text')}] {text}")
    return "\n".join(lines)
