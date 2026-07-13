from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from .catalog_seed import CATALOG_SEED, CATALOG_TABLE_SQL, ORDERS_TABLE_SQL
from .faq_content import build_delivery_faq_answer, resolve_faq_item, resolve_brand_city
from .escalation_cases import ESCALATION_CASES_SQL, funnel_snapshot_has_value, kind_from_reasons
from .funnel import WIZARD_STAGES
from .managers_config import (
    DEFAULT_MANAGERS_CONFIG,
    MANAGERS_CONFIG_KEY,
    ManagersConfig,
    parse_managers_config,
    serialize_managers_config,
)

try:
    from src.catalog_media import catalog_media_path
except ImportError:
    from catalog_media import catalog_media_path  # type: ignore[no-redef]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    username TEXT,
    full_name TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dialogs (
    id BIGSERIAL PRIMARY KEY,
    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    direction TEXT NOT NULL DEFAULT 'in',
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_events (
    id BIGSERIAL PRIMARY KEY,
    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS faq_items (
    id BIGSERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    answer TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS escalation_rules (
    id BIGSERIAL PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS product_classes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    price_from NUMERIC(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS countertop_materials (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    price_from NUMERIC(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS service_fees (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    value NUMERIC(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS voice_retry_state (
    user_id BIGINT PRIMARY KEY,
    retry_count INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS config_change_log (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id BIGINT NOT NULL,
    entity TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    old_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_status_created_at ON leads(status, created_at);
CREATE INDEX IF NOT EXISTS idx_dialogs_lead_created_at ON dialogs(lead_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_lead_created_at ON lead_events(lead_id, created_at);
""" + CATALOG_TABLE_SQL + ORDERS_TABLE_SQL + ESCALATION_CASES_SQL


FAQ_SEED: list[tuple[str, str]] = [
    ("цена", "Ориентировочно: Эконом от 25 000 ₽/пог.м, Стандарт от 38 000 ₽/пог.м, Премиум от 55 000 ₽/пог.м."),
    ("срок", "Обычно от обращения до установки 3-6 недель, зависит от материалов и сложности."),
    ("материал", "Фасады: ЛДСП, МДФ в пленке ПВХ, МДФ в эмали/HPL. Столешницы: ЛДСП, акрил, кварц."),
    ("доставка", "Доставка по городу и за город — тарифы из настроек прайса."),
    ("гарантия", "Гарантия: 24 месяца на корпус/фасады, 12 месяцев на фурнитуру и механизмы."),
]

ESCALATION_SEED: list[str] = [
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
]

PRODUCT_CLASSES_SEED: list[tuple[str, float]] = [
    ("эконом", 25000.0),
    ("стандарт", 38000.0),
    ("премиум", 55000.0),
]

COUNTERTOPS_SEED: list[tuple[str, float]] = [
    ("лдсп", 2500.0),
    ("акрил", 9000.0),
    ("кварц", 14000.0),
    ("массив", 18000.0),
]

SERVICE_FEES_SEED: list[tuple[str, float]] = [
    ("delivery_city_free_threshold", 150000.0),
    ("delivery_city_fixed", 3000.0),
    ("delivery_outside_base", 5000.0),
    ("delivery_outside_per_km", 50.0),
    ("assembly_percent", 0.15),
    ("assembly_min", 12000.0),
]


@dataclass
class PostgresStorage:
    dsn: str

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn, autocommit=True)

    def ensure_schema_and_seed(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.executemany(
                "INSERT INTO faq_items(key, answer) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                FAQ_SEED,
            )
            cur.executemany(
                "INSERT INTO escalation_rules(keyword) VALUES (%s) ON CONFLICT (keyword) DO NOTHING",
                [(item,) for item in ESCALATION_SEED],
            )
            cur.executemany(
                "INSERT INTO product_classes(code, price_from) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING",
                PRODUCT_CLASSES_SEED,
            )
            cur.executemany(
                "INSERT INTO countertop_materials(code, price_from) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING",
                COUNTERTOPS_SEED,
            )
            cur.executemany(
                "INSERT INTO service_fees(code, value) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING",
                SERVICE_FEES_SEED,
            )
            cur.executemany(
                """
                INSERT INTO catalog_items(category, code, title, description, price_from, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (category, code) DO NOTHING
                """,
                CATALOG_SEED,
            )

    def _upsert_lead(self, user_id: int) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads(user_id)
                VALUES (%s)
                ON CONFLICT (user_id)
                DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return int(row[0])

    def ensure_lead_profile(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        username: str | None = None,
    ) -> None:
        lead_id = self._upsert_lead(user_id)
        clean_name = (full_name or "").strip() or None
        clean_user = (username or "").strip().lstrip("@") or None
        if not clean_name and not clean_user:
            return
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET full_name = COALESCE(%s, full_name),
                    username = COALESCE(%s, username),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (clean_name, clean_user, lead_id),
            )

    def add_request(self, user_id: int, text: str, source: str) -> None:
        lead_id = self._upsert_lead(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dialogs(lead_id, source, text)
                VALUES (%s, %s, %s)
                """,
                (lead_id, source, text),
            )

    def add_event(self, user_id: int, event_type: str, payload: dict[str, Any]) -> None:
        lead_id = self._upsert_lead(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lead_events(lead_id, event_type, payload_json)
                VALUES (%s, %s, %s::jsonb)
                """,
                (lead_id, event_type, json.dumps(payload, ensure_ascii=False)),
            )

    def get_app_setting(self, key: str) -> str | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return str(row[0]).strip() or None

    def get_brand_city(self) -> str:
        return resolve_brand_city(
            brand_city=self.get_app_setting("brand_city"),
            timezone=self.get_app_setting("timezone"),
        )

    def get_timezone(self) -> str:
        return self.get_app_setting("timezone") or "Asia/Irkutsk"

    def get_brand_name(self) -> str:
        return self.get_app_setting("brand_name") or "АртКухня"

    def get_managers_config(self) -> ManagersConfig:
        return parse_managers_config(self.get_app_setting(MANAGERS_CONFIG_KEY))

    def set_managers_config(self, config: ManagersConfig) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW()
                """,
                (MANAGERS_CONFIG_KEY, serialize_managers_config(config)),
            )

    def get_faq_match(self, text: str) -> tuple[str, str] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT key, answer
                FROM faq_items
                WHERE is_active = TRUE
                ORDER BY id ASC
                """
            )
            rows = [(str(key), str(answer)) for key, answer in cur.fetchall() if key]

        def delivery_answer() -> str:
            fees = self.get_pricing_reference().get("service_fees", {})
            return build_delivery_faq_answer(city=self.get_brand_city(), service_fees=fees)

        return resolve_faq_item(text, rows, special_answers={"доставка": delivery_answer})

    def get_faq_answer(self, text: str) -> str | None:
        match = self.get_faq_match(text)
        return match[1] if match else None

    def get_escalation_keywords(self) -> list[str]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT keyword
                FROM escalation_rules
                WHERE is_active = TRUE
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
        return [str(row[0]) for row in rows if row and row[0]]

    def get_pricing_reference(self) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT code, price_from FROM product_classes WHERE is_active = TRUE ORDER BY id ASC"
            )
            product_rows = cur.fetchall()
            cur.execute(
                "SELECT code, price_from FROM countertop_materials WHERE is_active = TRUE ORDER BY id ASC"
            )
            countertop_rows = cur.fetchall()
            cur.execute(
                "SELECT code, value FROM service_fees WHERE is_active = TRUE ORDER BY id ASC"
            )
            fee_rows = cur.fetchall()

        return {
            "product_classes": {str(code): float(price) for code, price in product_rows},
            "countertops": {str(code): float(price) for code, price in countertop_rows},
            "service_fees": {str(code): float(value) for code, value in fee_rows},
        }

    def get_user_message_count(self, user_id: int) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM dialogs d
                JOIN leads l ON l.id = d.lead_id
                WHERE l.user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_bot_message_count(self, user_id: int) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM lead_events e
                JOIN leads l ON l.id = e.lead_id
                WHERE l.user_id = %s AND e.event_type = 'bot_reply'
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_session_user_message_count(self, user_id: int) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM dialogs d
                JOIN leads l ON l.id = d.lead_id
                WHERE l.user_id = %s
                  AND d.created_at >= COALESCE(
                    (
                        SELECT MAX(e.created_at)
                        FROM lead_events e
                        JOIN leads l2 ON l2.id = e.lead_id
                        WHERE l2.user_id = %s AND e.event_type = 'session_start'
                    ),
                    '1970-01-01'::timestamptz
                  )
                """,
                (user_id, user_id),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_session_bot_message_count(self, user_id: int) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM lead_events e
                JOIN leads l ON l.id = e.lead_id
                WHERE l.user_id = %s
                  AND e.event_type = 'bot_reply'
                  AND e.created_at >= COALESCE(
                    (
                        SELECT MAX(e2.created_at)
                        FROM lead_events e2
                        JOIN leads l2 ON l2.id = e2.lead_id
                        WHERE l2.user_id = %s AND e2.event_type = 'session_start'
                    ),
                    '1970-01-01'::timestamptz
                  )
                """,
                (user_id, user_id),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_voice_retry_count(self, user_id: int) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT retry_count FROM voice_retry_state WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def increment_voice_retry_count(self, user_id: int) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO voice_retry_state(user_id, retry_count)
                VALUES (%s, 1)
                ON CONFLICT (user_id)
                DO UPDATE SET retry_count = voice_retry_state.retry_count + 1, updated_at = NOW()
                RETURNING retry_count
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 1

    def reset_voice_retry_count(self, user_id: int) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO voice_retry_state(user_id, retry_count)
                VALUES (%s, 0)
                ON CONFLICT (user_id)
                DO UPDATE SET retry_count = 0, updated_at = NOW()
                """,
                (user_id,),
            )

    def get_daily_summary(self, now_utc: datetime | None = None) -> dict[str, int]:
        now = now_utc or datetime.now(timezone.utc)
        day_start = now - timedelta(days=1)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM leads WHERE created_at >= %s",
                (day_start,),
            )
            new_leads = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COUNT(*)
                FROM lead_events
                WHERE created_at >= %s AND event_type = 'escalation_sent'
                """,
                (day_start,),
            )
            escalated = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COUNT(*)
                FROM dialogs
                WHERE created_at >= %s
                """,
                (day_start,),
            )
            activity = int(cur.fetchone()[0])

        return {
            "new_leads": new_leads,
            "escalated": escalated,
            "activity": activity,
        }

    def admin_set_faq(self, actor_user_id: int, key: str, answer: str) -> None:
        key_norm = key.lower()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT answer, is_active FROM faq_items WHERE key = %s",
                (key_norm,),
            )
            old_row = cur.fetchone()
            old_data = {
                "answer": old_row[0] if old_row else None,
                "is_active": bool(old_row[1]) if old_row else None,
            }
            cur.execute(
                """
                INSERT INTO faq_items(key, answer, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (key)
                DO UPDATE SET answer = EXCLUDED.answer, is_active = TRUE
                """,
                (key_norm, answer),
            )
            cur.execute(
                """
                INSERT INTO config_change_log(actor_user_id, entity, entity_key, old_json, new_json)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    actor_user_id,
                    "faq_items",
                    key_norm,
                    json.dumps(old_data, ensure_ascii=False),
                    json.dumps({"answer": answer, "is_active": True}, ensure_ascii=False),
                ),
            )

    def admin_set_escalation_keyword(self, actor_user_id: int, keyword: str, is_active: bool) -> None:
        key_norm = keyword.lower()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT is_active FROM escalation_rules WHERE keyword = %s",
                (key_norm,),
            )
            old_row = cur.fetchone()
            old_data = {"is_active": bool(old_row[0]) if old_row else None}
            cur.execute(
                """
                INSERT INTO escalation_rules(keyword, is_active)
                VALUES (%s, %s)
                ON CONFLICT (keyword)
                DO UPDATE SET is_active = EXCLUDED.is_active
                """,
                (key_norm, is_active),
            )
            cur.execute(
                """
                INSERT INTO config_change_log(actor_user_id, entity, entity_key, old_json, new_json)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    actor_user_id,
                    "escalation_rules",
                    key_norm,
                    json.dumps(old_data, ensure_ascii=False),
                    json.dumps({"is_active": is_active}, ensure_ascii=False),
                ),
            )

    def admin_set_service_fee(self, actor_user_id: int, code: str, value: float) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT value, is_active FROM service_fees WHERE code = %s",
                (code,),
            )
            old_row = cur.fetchone()
            old_data = {
                "value": float(old_row[0]) if old_row else None,
                "is_active": bool(old_row[1]) if old_row else None,
            }
            cur.execute(
                """
                INSERT INTO service_fees(code, value, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (code)
                DO UPDATE SET value = EXCLUDED.value, is_active = TRUE
                """,
                (code, value),
            )
            cur.execute(
                """
                INSERT INTO config_change_log(actor_user_id, entity, entity_key, old_json, new_json)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    actor_user_id,
                    "service_fees",
                    code,
                    json.dumps(old_data, ensure_ascii=False),
                    json.dumps({"value": value, "is_active": True}, ensure_ascii=False),
                ),
            )

    def admin_list_faq(self) -> list[tuple[str, str]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT key, answer FROM faq_items WHERE is_active = TRUE ORDER BY key ASC"
            )
            rows = cur.fetchall()
        return [(str(key), str(answer)) for key, answer in rows]

    def admin_get_faq(self, key: str) -> str | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT answer FROM faq_items WHERE key = %s AND is_active = TRUE",
                (key.lower(),),
            )
            row = cur.fetchone()
        return str(row[0]) if row else None

    def admin_list_escalation_rules(self) -> list[tuple[str, bool]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT keyword, is_active FROM escalation_rules ORDER BY keyword ASC")
            rows = cur.fetchall()
        return [(str(keyword), bool(active)) for keyword, active in rows]

    def admin_list_service_fees(self) -> list[tuple[str, float]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT code, value FROM service_fees WHERE is_active = TRUE ORDER BY code ASC"
            )
            rows = cur.fetchall()
        return [(str(code), float(value)) for code, value in rows]

    def get_funnel_state(self, user_id: int) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.payload_json
                FROM lead_events e
                JOIN leads l ON l.id = e.lead_id
                WHERE l.user_id = %s AND e.event_type = 'funnel_state'
                ORDER BY e.created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
        if not row or not row[0]:
            return {}
        payload = row[0]
        if isinstance(payload, str):
            return json.loads(payload)
        return dict(payload)

    def set_funnel_state(self, user_id: int, state: dict[str, Any]) -> None:
        self.add_event(user_id, "funnel_state", state)
        self._sync_funnel_watch(user_id, state)

    def clear_funnel_state(self, user_id: int) -> None:
        self.set_funnel_state(user_id, {})
        self._remove_funnel_watch(user_id)

    def _sync_funnel_watch(self, user_id: int, state: dict[str, Any]) -> None:
        stage = str(state.get("stage") or "idle")
        if stage in WIZARD_STAGES and stage != "done" and funnel_snapshot_has_value(state):
            lead_id = self._upsert_lead(user_id)
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO funnel_watch(user_id, lead_id, stage, state_json, updated_at, abandoned_escalated_at)
                    VALUES (%s, %s, %s, %s::jsonb, NOW(), NULL)
                    ON CONFLICT (user_id) DO UPDATE SET
                        lead_id = EXCLUDED.lead_id,
                        stage = EXCLUDED.stage,
                        state_json = EXCLUDED.state_json,
                        updated_at = NOW(),
                        abandoned_escalated_at = NULL
                    """,
                    (user_id, lead_id, stage, json.dumps(state, ensure_ascii=False)),
                )
        else:
            self._remove_funnel_watch(user_id)

    def _remove_funnel_watch(self, user_id: int) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM funnel_watch WHERE user_id = %s", (user_id,))

    def list_stale_funnel_sessions(self, *, timeout_minutes: int) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT fw.user_id, fw.stage, fw.state_json, l.full_name, l.username
                FROM funnel_watch fw
                JOIN leads l ON l.id = fw.lead_id
                WHERE fw.abandoned_escalated_at IS NULL
                  AND fw.updated_at <= NOW() - (%s || ' minutes')::interval
                ORDER BY fw.updated_at ASC
                LIMIT 50
                """,
                (max(1, timeout_minutes),),
            )
            rows = cur.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = row[2]
            if isinstance(payload, str):
                state_json = json.loads(payload)
            else:
                state_json = dict(payload or {})
            result.append(
                {
                    "user_id": int(row[0]),
                    "stage": str(row[1]),
                    "state_json": state_json,
                    "full_name": row[3],
                    "username": row[4],
                }
            )
        return result

    def mark_funnel_abandoned_escalated(self, user_id: int) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE funnel_watch SET abandoned_escalated_at = NOW() WHERE user_id = %s",
                (user_id,),
            )

    def record_escalation_case(
        self,
        *,
        user_id: int,
        kind: str,
        reasons: list[str],
        summary: str,
        funnel_snapshot: dict[str, Any] | None = None,
        order_id: int | None = None,
        manager_id: str | None = None,
        manager_name: str | None = None,
        phone: str | None = None,
        full_name: str | None = None,
        username: str | None = None,
        notified: bool = False,
    ) -> int:
        lead_id = self._upsert_lead(user_id)
        status = "linked_order" if order_id else "new"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT username, full_name FROM leads WHERE id = %s",
                (lead_id,),
            )
            lead_row = cur.fetchone()
            if lead_row:
                username = username or lead_row[0]
                full_name = full_name or lead_row[1]
            cur.execute(
                """
                INSERT INTO escalation_cases(
                    lead_id, user_id, kind, reasons, summary, funnel_snapshot, order_id,
                    manager_id, manager_name, phone, full_name, username, status, notified_at
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    lead_id,
                    user_id,
                    kind,
                    json.dumps(reasons, ensure_ascii=False),
                    summary,
                    json.dumps(funnel_snapshot or {}, ensure_ascii=False),
                    order_id,
                    manager_id,
                    manager_name,
                    phone,
                    full_name,
                    username,
                    status,
                    datetime.now(timezone.utc) if notified else None,
                ),
            )
            return int(cur.fetchone()[0])

    def admin_list_escalation_cases(
        self,
        *,
        query: str = "",
        kind: str = "",
        has_order: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT id, kind, reasons, summary, order_id, manager_name, phone, full_name, username,
                   user_id, status, created_at
            FROM escalation_cases
            WHERE 1=1
        """
        params: list[Any] = []
        if kind:
            sql += " AND kind = %s"
            params.append(kind)
        if has_order == "yes":
            sql += " AND order_id IS NOT NULL"
        elif has_order == "no":
            sql += " AND order_id IS NULL"
        if query.strip():
            sql += " AND (summary ILIKE %s OR phone ILIKE %s OR full_name ILIKE %s OR username ILIKE %s OR CAST(user_id AS TEXT) ILIKE %s)"
            pattern = f"%{query.strip()}%"
            params.extend([pattern] * 5)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(max(1, min(limit, 100)))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._escalation_case_row(row) for row in rows]

    def admin_get_escalation_case(self, case_id: int) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, kind, reasons, summary, funnel_snapshot, order_id, manager_id, manager_name,
                       phone, full_name, username, user_id, status, created_at, notified_at
                FROM escalation_cases
                WHERE id = %s
                """,
                (case_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        reasons = row[2]
        if isinstance(reasons, str):
            reasons_list = json.loads(reasons)
        else:
            reasons_list = list(reasons or [])
        snapshot = row[4]
        if isinstance(snapshot, str):
            funnel_snapshot = json.loads(snapshot)
        else:
            funnel_snapshot = dict(snapshot or {})
        return {
            "id": int(row[0]),
            "kind": str(row[1]),
            "reasons": reasons_list,
            "summary": str(row[3] or ""),
            "funnel_snapshot": funnel_snapshot,
            "order_id": int(row[5]) if row[5] is not None else None,
            "manager_id": row[6],
            "manager_name": row[7],
            "phone": row[8],
            "full_name": row[9],
            "username": row[10],
            "user_id": int(row[11]),
            "status": str(row[12]),
            "created_at": row[13].isoformat() if row[13] else None,
            "notified_at": row[14].isoformat() if row[14] else None,
        }

    def _escalation_case_row(self, row: tuple[Any, ...]) -> dict[str, Any]:
        reasons = row[2]
        if isinstance(reasons, str):
            reasons_list = json.loads(reasons)
        else:
            reasons_list = list(reasons or [])
        return {
            "id": int(row[0]),
            "kind": str(row[1]),
            "reasons": reasons_list,
            "summary": str(row[3] or ""),
            "order_id": int(row[4]) if row[4] is not None else None,
            "manager_name": row[5],
            "phone": row[6],
            "full_name": row[7],
            "username": row[8],
            "user_id": int(row[9]),
            "status": str(row[10]),
            "created_at": row[11].isoformat() if row[11] else None,
        }

    def list_catalog(self, category: str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, category, code, title, description, price_from,
                       telegram_file_id, is_active, sort_order,
                       (image_thumb IS NOT NULL) AS has_image
                FROM catalog_items
                WHERE category = %s AND is_active = TRUE
                ORDER BY sort_order ASC, title ASC
                """,
                (category,),
            )
            rows = cur.fetchall()
        return [self._catalog_row_to_dict(row) for row in rows]

    def _catalog_row_to_dict(self, row: tuple[Any, ...]) -> dict[str, Any]:
        item_id = int(row[0])
        has_image = bool(row[9])
        return {
            "id": item_id,
            "category": str(row[1]),
            "code": str(row[2]),
            "title": str(row[3]),
            "description": str(row[4] or ""),
            "price_from": float(row[5]) if row[5] is not None else None,
            "image_path": catalog_media_path(item_id, "master") if has_image else None,
            "image_thumb_path": catalog_media_path(item_id, "thumb") if has_image else None,
            "has_image": has_image,
            "telegram_file_id": str(row[6]) if row[6] else None,
            "is_active": bool(row[7]),
            "sort_order": int(row[8]),
        }

    def get_catalog_item(self, category: str, code: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, category, code, title, description, price_from,
                       telegram_file_id, is_active, sort_order,
                       (image_thumb IS NOT NULL) AS has_image
                FROM catalog_items
                WHERE category = %s AND code = %s AND is_active = TRUE
                LIMIT 1
                """,
                (category, code),
            )
            row = cur.fetchone()
        if not row:
            return None
        return self._catalog_row_to_dict(row)

    def get_catalog_image_bytes(self, item_id: int, size: str = "master") -> bytes | None:
        column = "image_thumb" if size == "thumb" else "image_master"
        with self._connect() as conn, conn.cursor() as cur:
            if column == "image_thumb":
                cur.execute("SELECT image_thumb FROM catalog_items WHERE id = %s", (item_id,))
            else:
                cur.execute("SELECT image_master FROM catalog_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return bytes(row[0])

    def set_catalog_telegram_file_id(self, item_id: int, file_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE catalog_items SET telegram_file_id = %s, updated_at = NOW() WHERE id = %s",
                (file_id, item_id),
            )

    def create_order(self, user_id: int, payload: dict[str, Any]) -> int:
        lead_id = self._upsert_lead(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders(
                    lead_id, status, style_code, facade_code, countertop_code, hardware_code,
                    length_m, shape, phone, name, estimate_total
                )
                VALUES (%s, 'new', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    lead_id,
                    payload.get("style_code"),
                    payload.get("facade_code"),
                    payload.get("countertop_code"),
                    payload.get("hardware_code"),
                    payload.get("length_m"),
                    payload.get("shape"),
                    payload.get("phone"),
                    payload.get("name"),
                    payload.get("estimate_total"),
                ),
            )
            order_id = int(cur.fetchone()[0])
            cur.execute(
                "UPDATE leads SET status = 'ordered', updated_at = NOW() WHERE id = %s",
                (lead_id,),
            )
        self.add_event(
            user_id,
            "order_created",
            {"order_id": order_id, **payload},
        )
        return order_id

    def admin_list_orders(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, o.status, o.style_code, o.facade_code, o.countertop_code, o.hardware_code,
                       o.length_m, o.shape, o.phone, o.name, o.estimate_total, o.created_at,
                       o.lead_id, l.user_id, l.username, l.full_name
                FROM orders o
                JOIN leads l ON l.id = o.lead_id
                ORDER BY o.created_at DESC
                LIMIT %s
                """,
                (max(1, min(limit, 50)),),
            )
            rows = cur.fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                titles = self._order_catalog_titles(
                    cur,
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                )
                result.append(self._order_dict_from_row(row, titles))
        return result

    def admin_get_order(self, order_id: int) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, o.status, o.style_code, o.facade_code, o.countertop_code, o.hardware_code,
                       o.length_m, o.shape, o.phone, o.name, o.estimate_total, o.created_at,
                       o.lead_id, l.user_id, l.username, l.full_name
                FROM orders o
                JOIN leads l ON l.id = o.lead_id
                WHERE o.id = %s
                """,
                (order_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            titles = self._order_catalog_titles(cur, row[2], row[3], row[4], row[5])
            return self._order_dict_from_row(row, titles)

    def admin_list_order_dialogs(self, order_id: int, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT lead_id FROM orders WHERE id = %s", (order_id,))
            row = cur.fetchone()
            if not row:
                return []
            cur.execute(
                """
                SELECT source, text, created_at
                FROM dialogs
                WHERE lead_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (int(row[0]), max(1, min(limit, 200))),
            )
            rows = cur.fetchall()
        return [
            {
                "source": str(source),
                "text": str(text),
                "created_at": created_at.isoformat() if created_at else None,
            }
            for source, text, created_at in rows
        ]

    def _order_catalog_titles(
        self,
        cur: psycopg.Cursor,
        style_code: Any,
        facade_code: Any,
        countertop_code: Any,
        hardware_code: Any,
    ) -> dict[str, str | None]:
        titles: dict[str, str | None] = {}
        for category, code in (
            ("style", style_code),
            ("facade", facade_code),
            ("countertop", countertop_code),
            ("hardware", hardware_code),
        ):
            if not code:
                titles[category] = None
                continue
            cur.execute(
                "SELECT title FROM catalog_items WHERE category = %s AND code = %s LIMIT 1",
                (category, code),
            )
            item = cur.fetchone()
            titles[category] = str(item[0]) if item else None
        return titles

    def _order_dict_from_row(self, row: tuple[Any, ...], titles: dict[str, str | None]) -> dict[str, Any]:
        return {
            "id": int(row[0]),
            "status": str(row[1]),
            "style_code": row[2],
            "facade_code": row[3],
            "countertop_code": row[4],
            "hardware_code": row[5],
            "length_m": float(row[6]) if row[6] is not None else None,
            "shape": row[7],
            "phone": row[8],
            "name": row[9],
            "estimate_total": float(row[10]) if row[10] is not None else None,
            "created_at": row[11].isoformat() if row[11] else None,
            "lead_id": int(row[12]),
            "user_id": int(row[13]) if row[13] is not None else None,
            "username": row[14],
            "full_name": row[15],
            "style_title": titles.get("style"),
            "facade_title": titles.get("facade"),
            "countertop_title": titles.get("countertop"),
            "hardware_title": titles.get("hardware"),
        }
