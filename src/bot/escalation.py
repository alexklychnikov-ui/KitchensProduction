from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .managers_config import (
    DEFAULT_MANAGERS_CONFIG,
    DayHours,
    ManagerProfile,
    ManagersConfig,
    OfficeHours,
    build_client_escalation_message,
    build_manager_notification,
    resolve_manager,
)

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
    "заказать",
    "рассчитать точно",
    "оплатить",
    "брак",
    "вернуть деньги",
    "директор",
)


def should_escalate(text: str, keywords: list[str] | tuple[str, ...] = DEFAULT_ESCALATION_KEYWORDS) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in keywords)


@dataclass(frozen=True)
class EscalationDecision:
    should_escalate: bool
    reasons: list[str]


def _local_hour(now_utc: datetime, timezone_name: str) -> tuple[int, float]:
    local = now_utc.astimezone(ZoneInfo(timezone_name))
    hour = local.hour + local.minute / 60
    return local.weekday(), hour


def is_outside_working_hours(
    now_utc: datetime | None = None,
    *,
    timezone_name: str = "Asia/Irkutsk",
    office_hours: OfficeHours | None = None,
) -> bool:
    utc_now = now_utc or datetime.now(timezone.utc)
    hours = office_hours or DEFAULT_MANAGERS_CONFIG.office_hours
    weekday, hour = _local_hour(utc_now, timezone_name)
    if weekday == 6:
        return hours.sunday is None or not hours.sunday.contains_hour(hour)
    if weekday == 5:
        if hours.saturday is None:
            return True
        return not hours.saturday.contains_hour(hour)
    return not hours.mon_fri.contains_hour(hour)


def _next_open_hint(now_utc: datetime, timezone_name: str, office_hours: OfficeHours) -> str:
    local = now_utc.astimezone(ZoneInfo(timezone_name))
    weekday = local.weekday()
    if weekday == 6 or (weekday == 5 and office_hours.saturday is None):
        return "в понедельник с 9:00"
    if weekday == 5 and office_hours.saturday and local.hour >= office_hours.saturday.end:
        return "в понедельник с 9:00"
    if weekday < 5 and local.hour >= office_hours.mon_fri.end:
        if weekday == 4 and office_hours.saturday:
            return "в субботу с 9:00"
        return "завтра с 9:00"
    if local.hour < office_hours.mon_fri.start:
        return f"сегодня с {office_hours.mon_fri.start}:00"
    return "в начале следующего рабочего дня"


def after_hours_note(
    now_utc: datetime | None = None,
    *,
    timezone_name: str = "Asia/Irkutsk",
    office_hours: OfficeHours | None = None,
) -> str | None:
    hours = office_hours or DEFAULT_MANAGERS_CONFIG.office_hours
    utc_now = now_utc or datetime.now(timezone.utc)
    if not is_outside_working_hours(utc_now, timezone_name=timezone_name, office_hours=hours):
        return None
    hint = _next_open_hint(utc_now, timezone_name, hours)
    return (
        f"\n\nСейчас вне рабочего времени. "
        f"Менеджер ответит {hint}."
    )


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


def prepare_escalation_reply(
    *,
    config: ManagersConfig,
    timezone_name: str,
    reasons: list[str],
    source_text: str,
    full_name: str,
    username: str,
    user_id: int,
    now_utc: datetime | None = None,
) -> tuple[str, str, ManagerProfile]:
    utc_now = now_utc or datetime.now(timezone.utc)
    outside_hours = is_outside_working_hours(
        utc_now,
        timezone_name=timezone_name,
        office_hours=config.office_hours,
    )
    manager = resolve_manager(
        config=config,
        reasons=reasons,
        source_text=source_text,
        outside_hours=outside_hours,
    )
    urgent = "срочно" in source_text.lower()
    client_text = build_client_escalation_message(
        manager=manager,
        config=config,
        reasons=reasons,
        source_text=source_text,
        outside_hours=outside_hours,
    )
    note = after_hours_note(utc_now, timezone_name=timezone_name, office_hours=config.office_hours)
    if note:
        client_text = f"{client_text}{note}"
    notify_text = build_manager_notification(
        manager=manager,
        full_name=full_name,
        username=username,
        user_id=user_id,
        reasons=reasons,
        source_text=source_text,
        outside_hours=outside_hours,
        urgent=urgent,
    )
    return client_text, notify_text, manager
