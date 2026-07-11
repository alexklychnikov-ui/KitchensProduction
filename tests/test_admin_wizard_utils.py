from __future__ import annotations

from src.bot.admin_wizard import (
    TELEGRAM_MESSAGE_MAX,
    _build_faq_menu_text,
    _format_faq_saved_message,
    _truncate,
    _truncate_for_telegram,
    parse_fee_input,
)


def test_truncate_short_text() -> None:
    assert _truncate("hello world") == "hello world"


def test_truncate_long_text() -> None:
    text = "a" * 100
    result = _truncate(text, limit=10)
    assert len(result) == 10
    assert result.endswith("…")


def test_truncate_for_telegram_respects_limit() -> None:
    text = "x" * 5000
    result = _truncate_for_telegram(text, reserved=200)
    assert len(result) <= TELEGRAM_MESSAGE_MAX - 200


def test_build_faq_menu_text_within_limit() -> None:
    items = [(f"key{i}", "answer " * 200) for i in range(50)]
    text = _build_faq_menu_text(items)
    assert len(text) <= TELEGRAM_MESSAGE_MAX


def test_format_faq_saved_message_within_limit() -> None:
    long_answer = "z" * 5000
    text = _format_faq_saved_message("гарантия", long_answer, old="old")
    assert len(text) <= TELEGRAM_MESSAGE_MAX
    assert text.endswith("…")


def test_parse_fee_input_amount() -> None:
    value, error = parse_fee_input("15000", "assembly_min")
    assert error is None
    assert value == 15000.0


def test_parse_fee_input_amount_rejects_negative() -> None:
    value, error = parse_fee_input("-100", "assembly_min")
    assert value is None
    assert error is not None


def test_parse_fee_input_percent() -> None:
    value, error = parse_fee_input("15", "assembly_percent")
    assert error is None
    assert value == 0.15


def test_parse_fee_input_percent_range() -> None:
    value, error = parse_fee_input("101", "assembly_percent")
    assert value is None
    assert "0 до 100" in (error or "")


def test_parse_fee_input_percent_always_percent_not_fraction() -> None:
    value, error = parse_fee_input("0.15", "assembly_percent")
    assert error is None
    assert value == 0.0015
