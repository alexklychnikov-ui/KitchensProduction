from __future__ import annotations

from datetime import datetime, timezone

from src.bot.escalation import (
    after_hours_note,
    evaluate_escalation,
    is_outside_working_hours,
    should_escalate,
)


def test_should_escalate_keyword() -> None:
    assert should_escalate("Нужен менеджер", ["менеджер"]) is True
    assert should_escalate("просто вопрос", ["менеджер"]) is False


def test_evaluate_escalation_attachments() -> None:
    decision = evaluate_escalation(
        text="фото",
        keywords=[],
        has_attachments=True,
        bot_message_count=0,
        user_message_count=0,
    )
    assert decision.should_escalate is True
    assert "attachments" in decision.reasons


def test_evaluate_escalation_long_dialog_requires_both_counts() -> None:
    stalled = evaluate_escalation(
        text="hello",
        keywords=[],
        has_attachments=False,
        bot_message_count=10,
        user_message_count=8,
    )
    assert stalled.should_escalate is True
    assert "long_dialog" in stalled.reasons

    only_bot_replies = evaluate_escalation(
        text="привет",
        keywords=[],
        has_attachments=False,
        bot_message_count=15,
        user_message_count=2,
    )
    assert only_bot_replies.should_escalate is False


def test_outside_hours_does_not_auto_escalate() -> None:
    decision = evaluate_escalation(
        text="привет",
        keywords=[],
        has_attachments=False,
        bot_message_count=0,
        user_message_count=0,
    )
    assert decision.should_escalate is False
    assert "outside_working_hours" not in decision.reasons


def test_after_hours_note_on_sunday() -> None:
    sunday = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    assert is_outside_working_hours(sunday) is True
    assert after_hours_note(sunday) is not None


def test_after_hours_note_on_weekday_morning() -> None:
    monday_early = datetime(2026, 7, 13, 0, 30, tzinfo=timezone.utc)
    assert after_hours_note(monday_early) is not None


def test_after_hours_note_during_work_hours() -> None:
    saturday_noon = datetime(2026, 7, 11, 4, 0, tzinfo=timezone.utc)
    assert is_outside_working_hours(saturday_noon) is False
    assert after_hours_note(saturday_noon) is None
