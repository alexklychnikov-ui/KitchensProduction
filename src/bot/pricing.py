from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PRICE_INTENT_KEYWORDS = ("цена", "стоимость", "рассчитать", "расчёт", "расчет", "бюджет")

CLASS_LABELS: dict[str, str] = {
    "эконом": "Эконом",
    "стандарт": "Стандарт",
    "премиум": "Премиум",
}

CLASS_ORDER: tuple[str, ...] = ("эконом", "стандарт", "премиум")


def class_display_label(code: str) -> str:
    return CLASS_LABELS.get(code, code.capitalize())


def sorted_product_classes(product_classes: dict[str, Any]) -> list[tuple[str, float]]:
    known = [(code, float(product_classes[code])) for code in CLASS_ORDER if code in product_classes]
    rest = sorted(
        ((code, float(price)) for code, price in product_classes.items() if code not in CLASS_ORDER),
        key=lambda item: item[1],
    )
    return known + rest



STYLE_TO_CLASS: dict[str, str] = {
    "эконом": "эконом",
    "бюджет": "эконом",
    "дешев": "эконом",
    "премиум": "премиум",
    "люкс": "премиум",
    "элит": "премиум",
}


@dataclass(frozen=True)
class PricingResult:
    text: str
    matched: bool


@dataclass(frozen=True)
class EstimateResult:
    text: str
    total: float
    kitchen_class: str
    length_m: float


def detect_length(text: str, *, bare_number: bool = False) -> float | None:
    normalized = text.lower().strip().replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:м|метр|метра|метров|пог\.?м)\b", normalized)
    if match:
        return float(match.group(1))
    if bare_number:
        plain = re.match(r"^(\d+(?:\.\d+)?)$", normalized)
        if plain:
            value = float(plain.group(1))
            if 0.5 <= value <= 25:
                return value
    return None


def _detect_key(text: str, candidates: list[str]) -> str | None:
    normalized = text.lower()
    for key in candidates:
        if key in normalized:
            return key
    return None


def _style_to_class(style: str | None, normalized_text: str, product_classes: dict[str, Any]) -> str:
    if style:
        style_lower = style.lower()
        for token, kitchen_class in STYLE_TO_CLASS.items():
            if token in style_lower:
                return kitchen_class if kitchen_class in product_classes else "стандарт"
    detected = _detect_key(normalized_text, list(product_classes.keys()))
    return detected or "стандарт"


SHAPE_MULTIPLIERS: dict[str, float] = {
    "Прямая": 1.0,
    "Угловая": 1.1,
    "П-образная": 1.25,
    "Г-образная": 1.15,
}


def build_catalog_estimate(
    *,
    length_m: float,
    facade_price_pm: float,
    countertop_price_pm: float,
    style_title: str | None,
    facade_title: str | None,
    countertop_title: str | None,
    hardware_title: str | None,
    pricing_reference: dict[str, Any],
    shape: str | None = None,
    kitchen_class: str | None = None,
    hardware_price_pm: float = 0.0,
) -> EstimateResult:
    product_classes = pricing_reference.get("product_classes", {})
    class_code = kitchen_class or "стандарт"
    class_pm = float(product_classes.get(class_code, product_classes.get("стандарт", 38000.0)))
    service_fees = pricing_reference.get("service_fees", {})
    shape_factor = SHAPE_MULTIPLIERS.get(shape or "Прямая", 1.0)
    effective_length = length_m * shape_factor

    effective_facade_pm = max(class_pm, facade_price_pm)
    facades_total = effective_facade_pm * effective_length
    countertop_total = countertop_price_pm * effective_length
    hardware_total = hardware_price_pm * effective_length if hardware_price_pm > 0 else 0.0
    subtotal = facades_total + countertop_total + hardware_total

    assembly_percent = float(service_fees.get("assembly_percent", 0.15))
    assembly_min = float(service_fees.get("assembly_min", 12000.0))
    assembly_total = max(subtotal * assembly_percent, assembly_min)

    delivery_threshold = float(service_fees.get("delivery_city_free_threshold", 150000.0))
    delivery_city_fixed = float(service_fees.get("delivery_city_fixed", 3000.0))
    delivery_total = 0.0 if subtotal >= delivery_threshold else delivery_city_fixed

    total = subtotal + assembly_total + delivery_total
    shape_note = f", планировка «{shape}»" if shape else ""
    style_note = f", стиль «{style_title}»" if style_title else ""
    class_label = class_display_label(class_code)
    money = lambda v: f"{int(v):,}".replace(",", " ")

    facade_line = (
        f"Комплектация «{facade_title or '—'}»: {facades_total:,.0f} ₽ "
        f"(от {money(effective_facade_pm)} ₽/пог.м)"
    )
    if facade_price_pm < class_pm:
        facade_line += f" — база класса «{class_label}»"

    hardware_line = ""
    if hardware_total > 0:
        hardware_line = f"\nФурнитура «{hardware_title or '—'}»: {hardware_total:,.0f} ₽"

    result_text = (
        f"Ориентир по бюджету — класс «{class_label}»{style_note}{shape_note}, {length_m:.1f} м.\n"
        f"База класса: от {money(class_pm)} ₽/пог.м\n"
        f"{facade_line}\n"
        f"Столешница «{countertop_title or '—'}»: {countertop_total:,.0f} ₽"
        f"{hardware_line}\n"
        f"Монтаж: {assembly_total:,.0f} ₽\n"
        f"Доставка (по городу): {delivery_total:,.0f} ₽\n"
        f"Итого ориентировочно: {total:,.0f} ₽"
    ).replace(",", " ")
    return EstimateResult(
        text=result_text,
        total=total,
        kitchen_class=class_code,
        length_m=length_m,
    )


def build_estimate(
    *,
    length_m: float,
    style: str | None,
    pricing_reference: dict[str, Any],
    countertop: str | None = None,
    normalized_text: str = "",
) -> EstimateResult:
    product_classes = pricing_reference.get("product_classes", {})
    countertops = pricing_reference.get("countertops", {})
    service_fees = pricing_reference.get("service_fees", {})

    normalized = normalized_text.lower()
    kitchen_class = _style_to_class(style, normalized, product_classes)
    countertop_key = countertop or _detect_key(normalized, list(countertops.keys())) or "кварц"

    facade_pm = float(product_classes.get(kitchen_class, 38000.0))
    countertop_pm = float(countertops.get(countertop_key, 14000.0))

    facades_total = facade_pm * length_m
    countertop_total = countertop_pm * length_m
    subtotal = facades_total + countertop_total

    assembly_percent = float(service_fees.get("assembly_percent", 0.15))
    assembly_min = float(service_fees.get("assembly_min", 12000.0))
    assembly_total = max(subtotal * assembly_percent, assembly_min)

    delivery_threshold = float(service_fees.get("delivery_city_free_threshold", 150000.0))
    delivery_city_fixed = float(service_fees.get("delivery_city_fixed", 3000.0))
    delivery_total = 0.0 if subtotal >= delivery_threshold else delivery_city_fixed

    total = subtotal + assembly_total + delivery_total
    style_note = f", стиль «{style}»" if style else ""

    result_text = (
        f"Ориентир: класс «{kitchen_class.title()}»{style_note}, {length_m:.1f} м, столешница «{countertop_key}».\n"
        f"Фасады: {facades_total:,.0f} ₽\n"
        f"Столешница: {countertop_total:,.0f} ₽\n"
        f"Монтаж: {assembly_total:,.0f} ₽\n"
        f"Доставка (по городу): {delivery_total:,.0f} ₽\n"
        f"Итого ориентировочно: {total:,.0f} ₽"
    ).replace(",", " ")
    return EstimateResult(
        text=result_text,
        total=total,
        kitchen_class=kitchen_class,
        length_m=length_m,
    )


def maybe_calculate_price(text: str, pricing_reference: dict[str, Any]) -> PricingResult:
    normalized = text.lower()
    if not any(k in normalized for k in PRICE_INTENT_KEYWORDS):
        return PricingResult(text="", matched=False)

    length = detect_length(normalized) or 4.0
    estimate = build_estimate(
        length_m=length,
        style=None,
        pricing_reference=pricing_reference,
        normalized_text=normalized,
    )
    result_text = (
        f"{estimate.text}\n\n"
        "Точный расчёт — после замера. Могу записать на удобное время."
    )
    return PricingResult(text=result_text, matched=True)
