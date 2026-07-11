from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PRICE_INTENT_KEYWORDS = ("цена", "стоимость", "рассчитать", "расчёт", "расчет")

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
) -> EstimateResult:
    service_fees = pricing_reference.get("service_fees", {})
    shape_factor = SHAPE_MULTIPLIERS.get(shape or "Прямая", 1.0)
    effective_length = length_m * shape_factor

    facades_total = facade_price_pm * effective_length
    countertop_total = countertop_price_pm * effective_length
    subtotal = facades_total + countertop_total

    assembly_percent = float(service_fees.get("assembly_percent", 0.15))
    assembly_min = float(service_fees.get("assembly_min", 12000.0))
    assembly_total = max(subtotal * assembly_percent, assembly_min)

    delivery_threshold = float(service_fees.get("delivery_city_free_threshold", 150000.0))
    delivery_city_fixed = float(service_fees.get("delivery_city_fixed", 3000.0))
    delivery_total = 0.0 if subtotal >= delivery_threshold else delivery_city_fixed

    total = subtotal + assembly_total + delivery_total
    shape_note = f", планировка «{shape}»" if shape else ""
    style_note = f", стиль «{style_title}»" if style_title else ""

    result_text = (
        f"Ориентир{style_note}{shape_note}, {length_m:.1f} м.\n"
        f"Фасады «{facade_title or '—'}»: {facades_total:,.0f} ₽\n"
        f"Столешница «{countertop_title or '—'}»: {countertop_total:,.0f} ₽\n"
        f"Фурнитура «{hardware_title or '—'}»\n"
        f"Монтаж: {assembly_total:,.0f} ₽\n"
        f"Доставка (по городу): {delivery_total:,.0f} ₽\n"
        f"Итого ориентировочно: {total:,.0f} ₽"
    ).replace(",", " ")
    return EstimateResult(
        text=result_text,
        total=total,
        kitchen_class=facade_title or "стандарт",
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
