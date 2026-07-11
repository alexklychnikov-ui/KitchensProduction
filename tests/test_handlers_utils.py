from __future__ import annotations

from types import SimpleNamespace

from src.bot.handlers import _command_args, _is_client_text, _is_command


def _message(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def test_is_command_plain() -> None:
    assert _is_command("/admin", "/admin") is True
    assert _is_command("/admin help", "/admin") is True
    assert _is_command("/other", "/admin") is False
    assert _is_command(None, "/admin") is False


def test_is_command_with_botname() -> None:
    assert _is_command("/admin@MyKitchenBot", "/admin") is True
    assert _is_command("/admin@MyKitchenBot args", "/admin") is True


def test_command_args_plain() -> None:
    assert _command_args(_message("/cfg_faq_set цена|ответ"), "/cfg_faq_set") == "цена|ответ"


def test_command_args_with_botname() -> None:
    msg = _message("/cfg_faq_set@KitchenBot цена|новый ответ")
    assert _command_args(msg, "/cfg_faq_set") == "цена|новый ответ"


def test_command_args_wrong_command() -> None:
    assert _command_args(_message("/other x"), "/cfg_faq_set") == ""


def test_is_client_text() -> None:
    assert _is_client_text("привет") is True
    assert _is_client_text("/admin") is False
    assert _is_client_text("/admin@Bot") is False
    assert _is_client_text("  /start") is False
    assert _is_client_text("") is False
    assert _is_client_text(None) is False
