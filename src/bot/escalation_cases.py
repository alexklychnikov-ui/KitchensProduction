from __future__ import annotations

ESCALATION_CASES_SQL = """
CREATE TABLE IF NOT EXISTS escalation_cases (
    id BIGSERIAL PRIMARY KEY,
    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    kind TEXT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary TEXT NOT NULL DEFAULT '',
    funnel_snapshot JSONB,
    order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
    manager_id TEXT,
    manager_name TEXT,
    phone TEXT,
    full_name TEXT,
    username TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    notified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_escalation_cases_created_at ON escalation_cases(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_escalation_cases_kind ON escalation_cases(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_escalation_cases_order_id ON escalation_cases(order_id);

CREATE TABLE IF NOT EXISTS funnel_watch (
    user_id BIGINT PRIMARY KEY,
    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    state_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    abandoned_escalated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_funnel_watch_updated ON funnel_watch(updated_at);
"""

KIND_LABELS: dict[str, str] = {
    "order": "Заявка оформлена",
    "abandoned_funnel": "Брошенная воронка",
    "manager_request": "Запрос менеджера",
    "keyword": "Триггер-слово",
    "attachment": "Вложение",
    "stt_failed": "Голос не распознан",
    "long_dialog": "Длинный диалог",
    "other": "Другое",
}


def kind_from_reasons(reasons: list[str], *, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if "order_created" in reasons:
        return "order"
    if "abandoned_funnel" in reasons:
        return "abandoned_funnel"
    if "manager_requested" in reasons:
        return "manager_request"
    if "keyword_trigger" in reasons:
        return "keyword"
    if "attachments" in reasons:
        return "attachment"
    if "stt_failed" in reasons:
        return "stt_failed"
    if "long_dialog" in reasons:
        return "long_dialog"
    return "other"


def funnel_snapshot_has_value(state: dict) -> bool:
    if not state:
        return False
    return bool(
        state.get("style_code")
        or state.get("length_m") is not None
        or state.get("facade_code")
        or state.get("countertop_code")
        or state.get("hardware_code")
        or state.get("estimate_total") is not None
        or state.get("phone")
    )
