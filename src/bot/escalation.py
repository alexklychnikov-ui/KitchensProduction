from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DEFAULT_ESCALATION_KEYWORDS = (
    "менеджер",
    "человек",
    "оператор",
    "жалоба",
    "претенз",
    "точный расчет",
    "точный расчёт",
    "договор",
    "замер",
    "замерщик",
)


def should_escalate(text: str, keywords: list[str] | tuple[str, ...] = DEFAULT_ESCALATION_KEYWORDS) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in keywords)


@dataclass(frozen=True)
class EscalationDecision:
    should_escalate: bool
    reasons: list[str]


def is_outside_working_hours(now_utc: datetime | None = None) -> bool:
    utc_now = now_utc or datetime.now(timezone.utc)
    local = utc_now + timedelta(hours=8)
    weekday = local.weekday()
    hour = local.hour
    if weekday == 6:
        return True
    if weekday == 5:
        return hour < 9 or hour >= 19
    return hour < 9 or hour >= 19


def evaluate_escalation(
    *,
    text: str,
    keywords: list[str] | tuple[str, ...],
    has_attachments: bool,
    bot_message_count: int,
    user_message_count: int,
    stt_failed: bool = False,
) -> EscalationDecision:
    reasons: list[str] = []
    if should_escalate(text, keywords):
        reasons.append("keyword_trigger")
    if has_attachments:
        reasons.append("attachments")
    if bot_message_count >= 10 and user_message_count >= 8:
        reasons.append("long_dialog")
    if stt_failed:
        reasons.append("stt_failed")
    return EscalationDecision(should_escalate=bool(reasons), reasons=reasons)


def after_hours_note(now_utc: datetime | None = None) -> str | None:
    if is_outside_working_hours(now_utc):
        return (
            "\n\nСейчас вне рабочего времени. "
            "Менеджер ответит в начале следующего рабочего дня."
        )
    return None
