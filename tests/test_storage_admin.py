from __future__ import annotations

from src.bot.storage import InMemoryStorage


def test_admin_list_faq_sorted() -> None:
    storage = InMemoryStorage()
    storage.admin_set_faq(1, "zzz", "last")
    storage.admin_set_faq(1, "aaa", "first")
    keys = [key for key, _ in storage.admin_list_faq()]
    assert keys == sorted(keys)


def test_admin_get_faq() -> None:
    storage = InMemoryStorage()
    storage.admin_set_faq(1, "Акция", "Скидка 10%")
    assert storage.admin_get_faq("акция") == "Скидка 10%"
    assert storage.admin_get_faq("missing") is None


def test_escalation_toggle() -> None:
    storage = InMemoryStorage()
    storage.admin_set_escalation_keyword(1, "тест", True)
    assert "тест" in storage.get_escalation_keywords()
    storage.admin_set_escalation_keyword(1, "тест", False)
    assert "тест" not in storage.get_escalation_keywords()


def test_admin_list_service_fees() -> None:
    storage = InMemoryStorage()
    storage.admin_set_service_fee(1, "assembly_min", 20000.0)
    fees = dict(storage.admin_list_service_fees())
    assert fees["assembly_min"] == 20000.0


def test_session_counts_reset_after_start() -> None:
    storage = InMemoryStorage()
    user_id = 42
    storage.add_request(user_id, "old", "text")
    storage.add_event(user_id, "bot_reply", {"text": "old"})
    storage.add_event(user_id, "session_start", {})
    storage.add_request(user_id, "привет", "text")
    assert storage.get_user_message_count(user_id) == 2
    assert storage.get_session_user_message_count(user_id) == 1
    assert storage.get_bot_message_count(user_id) == 1
    assert storage.get_session_bot_message_count(user_id) == 0


def test_get_escalation_keywords_only_active() -> None:
    storage = InMemoryStorage()
    keywords = storage.get_escalation_keywords()
    assert isinstance(keywords, list)
    assert "менеджер" in keywords
