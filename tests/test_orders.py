from __future__ import annotations

from src.bot.orders import format_order_detail, format_order_short


def test_format_order_short() -> None:
    text = format_order_short({"id": 5, "phone": "+79991234567", "estimate_total": 180000, "created_at": None})
    assert "#5" in text
    assert "+79991234567" in text


def test_format_order_detail() -> None:
    text = format_order_detail(
        {
            "id": 1,
            "status": "new",
            "phone": "+7999",
            "style_title": "Скандинавский",
            "length_m": 3.2,
            "estimate_total": 200000,
        },
        [{"source": "text", "text": "хочу кухню"}],
    )
    assert "Заявка №1" in text
    assert "Скандинавский" in text
    assert "хочу кухню" in text
