from __future__ import annotations

from src.bot.faq_content import build_delivery_faq_answer, city_in_prepositional, resolve_brand_city
from src.bot.storage import InMemoryStorage


def test_resolve_brand_city_prefers_brand_city() -> None:
    assert resolve_brand_city(brand_city="Красноярск", timezone="Asia/Irkutsk") == "Красноярск"


def test_resolve_brand_city_from_timezone() -> None:
    assert resolve_brand_city(brand_city=None, timezone="Europe/Moscow") == "Москва"


def test_city_in_prepositional() -> None:
    assert city_in_prepositional("Иркутск") == "Иркутску"
    assert city_in_prepositional("Москва") == "Москве"


def test_delivery_faq_uses_city_and_fees() -> None:
    text = build_delivery_faq_answer(
        city="Красноярск",
        service_fees={
            "delivery_city_free_threshold": 150000,
            "delivery_city_fixed": 3000,
            "delivery_outside_base": 5000,
            "delivery_outside_per_km": 90,
        },
    )
    assert "Красноярску" in text
    assert "90 ₽/км" in text
    assert "150 000" in text


def test_inmemory_delivery_faq_dynamic() -> None:
    storage = InMemoryStorage(brand_city="Иркутск")
    answer = storage.get_faq_answer("сколько стоит доставка?")
    assert answer is not None
    assert "Иркутску" in answer
    assert "3 000" in answer

    storage.brand_city = "Москва"
    answer = storage.get_faq_answer("доставка")
    assert answer is not None
    assert "Москве" in answer
