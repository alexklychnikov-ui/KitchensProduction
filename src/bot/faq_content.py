from __future__ import annotations

from typing import Any

TIMEZONE_DEFAULT_CITY: dict[str, str] = {
    "Asia/Irkutsk": "Иркутск",
    "Asia/Krasnoyarsk": "Красноярск",
    "Asia/Novosibirsk": "Новосибирск",
    "Asia/Yekaterinburg": "Екатеринбург",
    "Europe/Moscow": "Москва",
    "UTC": "Иркутск",
}

CITY_DATIVE: dict[str, str] = {
    "Иркутск": "Иркутску",
    "Красноярск": "Красноярску",
    "Новосибирск": "Новосибирску",
    "Екатеринбург": "Екатеринбургу",
    "Москва": "Москве",
}


def _format_money(value: float | int) -> str:
    return f"{int(value):,}".replace(",", " ")


def city_in_prepositional(city: str) -> str:
    name = city.strip()
    if not name:
        return "городу"
    if name in CITY_DATIVE:
        return CITY_DATIVE[name]
    if name.endswith("ск"):
        return f"{name}у"
    if name.endswith("а"):
        return f"{name[:-1]}е"
    return name


def resolve_brand_city(*, brand_city: str | None, timezone: str | None) -> str:
    if brand_city and brand_city.strip():
        return brand_city.strip()
    if timezone and timezone in TIMEZONE_DEFAULT_CITY:
        return TIMEZONE_DEFAULT_CITY[timezone]
    return "Иркутск"


def build_delivery_faq_answer(*, city: str, service_fees: dict[str, Any]) -> str:
    threshold = float(service_fees.get("delivery_city_free_threshold", 150_000))
    city_fixed = float(service_fees.get("delivery_city_fixed", 3_000))
    outside_base = float(service_fees.get("delivery_outside_base", 5_000))
    per_km = float(service_fees.get("delivery_outside_per_km", 50))
    city_in = city_in_prepositional(city)
    return (
        f"По {city_in} бесплатно от {_format_money(threshold)} ₽, иначе {_format_money(city_fixed)} ₽. "
        f"За город: от {_format_money(outside_base)} ₽ + {_format_money(per_km)} ₽/км."
    )
