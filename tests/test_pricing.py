from __future__ import annotations

from src.bot.pricing import maybe_calculate_price
from src.bot.storage import InMemoryStorage


def test_maybe_calculate_price_sample() -> None:
    storage = InMemoryStorage()
    result = maybe_calculate_price(
        "Какая стоимость кухни стандарт 4 метра кварц?",
        storage.get_pricing_reference(),
    )
    assert result.matched is True
    assert "Ориентир" in result.text
    assert "₽" in result.text


def test_maybe_calculate_price_no_intent() -> None:
    storage = InMemoryStorage()
    result = maybe_calculate_price("Привет", storage.get_pricing_reference())
    assert result.matched is False
