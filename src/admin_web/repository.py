from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg

from src.bot.managers_config import (
    DEFAULT_MANAGERS_CONFIG,
    MANAGERS_CONFIG_KEY,
    ManagersConfig,
    managers_config_from_dict,
    managers_config_to_dict,
    parse_managers_config,
    serialize_managers_config,
)
from src.catalog_media import catalog_media_path

WEB_ADMIN_ACTOR = 0

ADMIN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS catalog_items (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price_from NUMERIC(12, 2),
    image_path TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(category, code)
);

CREATE INDEX IF NOT EXISTS idx_catalog_items_category_active
    ON catalog_items(category, is_active, sort_order);

ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS image_thumb_path TEXT;
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS image_width INT;
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS image_height INT;
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS telegram_file_id TEXT;
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS image_master BYTEA;
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS image_thumb BYTEA;
"""

DEFAULT_SETTINGS: dict[str, str] = {
    "timezone": "Asia/Irkutsk",
    "brand_name": "АртКухня",
    "brand_city": "Иркутск",
}

ADMIN_PASSWORD_HASH_KEY = "admin_password_hash"
ADMIN_PASSWORD_CHANGED_KEY = "admin_password_changed"
DEFAULT_ADMIN_PASSWORD = "1111"

CATALOG_SEED: list[tuple[str, str, str, str, float, int]] = [
    ("style", "modern_wood", "Современный с деревом", "Синий глянец, дерево, остров", 0, 1),
    ("style", "scandinavian", "Скандинавский", "Светлые фасады, мрамор, минимализм", 0, 2),
    ("style", "farmhouse", "Современный фермерский", "Серый шейкер, фартук, фарфор", 0, 3),
    ("facade", "mdf_white", "МДФ белый глянец", "Классический гладкий фасад", 38000, 1),
    ("facade", "mdf_wood", "МДФ под дерево", "Тёплая текстура дуба", 42000, 2),
    ("facade", "enamel_grey", "Эмаль серая", "Матовая эмаль премиум", 55000, 3),
    ("countertop", "quartz", "Кварц", "Износостойкая столешница", 14000, 1),
    ("countertop", "acrylic", "Акрил", "Бесшовные стыки", 9000, 2),
    ("countertop", "ldsp", "ЛДСП", "Бюджетный вариант", 2500, 3),
    ("hardware", "blum", "Blum", "Австрийская фурнитура", 0, 1),
    ("hardware", "hettich", "Hettich", "Немецкая фурнитура", 0, 2),
    ("hardware", "boyard", "Boyard", "Оптимальное соотношение цены", 0, 3),
]

FEE_LABELS: dict[str, str] = {
    "delivery_city_free_threshold": "Бесплатная доставка от, ₽",
    "delivery_city_fixed": "Доставка по городу, ₽",
    "delivery_outside_base": "Доставка за город, база, ₽",
    "delivery_outside_per_km": "За км за город, ₽",
    "assembly_percent": "Монтаж, % от стоимости",
    "assembly_min": "Монтаж минимум, ₽",
}


@dataclass(frozen=True)
class CatalogItem:
    id: int
    category: str
    code: str
    title: str
    description: str
    price_from: float | None
    image_path: str | None
    is_active: bool
    sort_order: int


class AdminRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url)

    def ensure_schema(self) -> None:
        from src.admin_web.auth import ensure_password_hash
        from src.bot.db_storage import PostgresStorage

        storage = PostgresStorage(self.database_url)
        storage.ensure_schema_and_seed()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(ADMIN_SCHEMA_SQL)
            for key, value in DEFAULT_SETTINGS.items():
                cur.execute(
                    """
                    INSERT INTO app_settings(key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO NOTHING
                    """,
                    (key, value),
                )
            cur.execute(
                "SELECT value FROM app_settings WHERE key = %s",
                (ADMIN_PASSWORD_HASH_KEY,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO app_settings(key, value)
                    VALUES (%s, %s)
                    """,
                    (
                        ADMIN_PASSWORD_HASH_KEY,
                        ensure_password_hash(DEFAULT_ADMIN_PASSWORD),
                    ),
                )
            cur.execute(
                "SELECT value FROM app_settings WHERE key = %s",
                (MANAGERS_CONFIG_KEY,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO app_settings(key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO NOTHING
                    """,
                    (MANAGERS_CONFIG_KEY, serialize_managers_config(DEFAULT_MANAGERS_CONFIG)),
                )
            for category, code, title, description, price_from, sort_order in CATALOG_SEED:
                cur.execute(
                    """
                    INSERT INTO catalog_items(category, code, title, description, price_from, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (category, code) DO NOTHING
                    """,
                    (category, code, title, description, price_from, sort_order),
                )

    def _audit(self, cur: psycopg.Cursor, entity: str, entity_key: str, old: Any, new: Any) -> None:
        cur.execute(
            """
            INSERT INTO config_change_log(actor_user_id, entity, entity_key, old_json, new_json)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                WEB_ADMIN_ACTOR,
                entity,
                entity_key,
                json.dumps(old, ensure_ascii=False),
                json.dumps(new, ensure_ascii=False),
            ),
        )

    def get_summary(self) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM leads WHERE created_at >= NOW() - INTERVAL '24 hours'")
            new_leads = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT COUNT(*) FROM lead_events
                WHERE event_type = 'escalation_sent' AND created_at >= NOW() - INTERVAL '24 hours'
                """
            )
            escalated = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM dialogs WHERE created_at >= NOW() - INTERVAL '24 hours'")
            activity = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM faq_items WHERE is_active = TRUE")
            faq_count = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM catalog_items WHERE is_active = TRUE")
            catalog_count = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM orders")
            orders_count = int(cur.fetchone()[0])
            cur.execute(
                "SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '24 hours'"
            )
            new_orders = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM escalation_cases")
            escalation_cases_count = int(cur.fetchone()[0])
            cur.execute(
                "SELECT COUNT(*) FROM escalation_cases WHERE order_id IS NOT NULL"
            )
            escalation_with_order = int(cur.fetchone()[0])
            cur.execute(
                "SELECT COUNT(*) FROM escalation_cases WHERE created_at >= NOW() - INTERVAL '24 hours'"
            )
            escalation_cases_24h = int(cur.fetchone()[0])
        return {
            "new_leads": new_leads,
            "escalated": escalated,
            "activity": activity,
            "faq_count": faq_count,
            "catalog_count": catalog_count,
            "orders_count": orders_count,
            "new_orders": new_orders,
            "escalation_cases_count": escalation_cases_count,
            "escalation_with_order": escalation_with_order,
            "escalation_cases_24h": escalation_cases_24h,
        }

    def list_settings(self) -> dict[str, str]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT key, value FROM app_settings ORDER BY key ASC")
            rows = cur.fetchall()
        return {str(key): str(value) for key, value in rows}

    def get_admin_password_hash(self) -> str | None:
        return self.list_settings().get(ADMIN_PASSWORD_HASH_KEY)

    def is_password_changed(self) -> bool:
        return self.list_settings().get(ADMIN_PASSWORD_CHANGED_KEY) == "1"

    def set_admin_password_hash(self, password_hash: str) -> None:
        self.set_setting(ADMIN_PASSWORD_HASH_KEY, password_hash)
        self.set_setting(ADMIN_PASSWORD_CHANGED_KEY, "1")

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            old_row = cur.fetchone()
            old_data = {"value": old_row[0] if old_row else None}
            cur.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                (key, value),
            )
            self._audit(cur, "app_settings", key, old_data, {"value": value})

    def get_managers_config(self) -> dict[str, Any]:
        raw = self.list_settings().get(MANAGERS_CONFIG_KEY)
        return managers_config_to_dict(parse_managers_config(raw))

    def set_managers_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = managers_config_from_dict(payload)
        serialized = serialize_managers_config(config)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (MANAGERS_CONFIG_KEY,))
            old_row = cur.fetchone()
            old_data = {"value": old_row[0] if old_row else None}
            cur.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                (MANAGERS_CONFIG_KEY, serialized),
            )
            self._audit(cur, "managers_config", MANAGERS_CONFIG_KEY, old_data, {"value": serialized})
        return managers_config_to_dict(config)

    def list_faq(self, query: str = "") -> list[dict[str, Any]]:
        sql = "SELECT key, answer, is_active FROM faq_items"
        params: list[Any] = []
        if query.strip():
            sql += " WHERE key ILIKE %s OR answer ILIKE %s"
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern])
        sql += " ORDER BY key ASC"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            {"key": str(key), "answer": str(answer), "is_active": bool(active)}
            for key, answer, active in rows
        ]

    def upsert_faq(self, key: str, answer: str, *, is_active: bool = True) -> None:
        key_norm = key.lower().strip()
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
                VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE
                SET answer = EXCLUDED.answer, is_active = EXCLUDED.is_active
                """,
                (key_norm, answer.strip(), is_active),
            )
            self._audit(
                cur,
                "faq_items",
                key_norm,
                old_data,
                {"answer": answer.strip(), "is_active": is_active},
            )

    def list_escalation(self, query: str = "") -> list[dict[str, Any]]:
        sql = "SELECT keyword, is_active FROM escalation_rules"
        params: list[Any] = []
        if query.strip():
            sql += " WHERE keyword ILIKE %s"
            params.append(f"%{query.strip()}%")
        sql += " ORDER BY keyword ASC"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [{"keyword": str(kw), "is_active": bool(active)} for kw, active in rows]

    def upsert_escalation(self, keyword: str, is_active: bool) -> None:
        key_norm = keyword.lower().strip()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT is_active FROM escalation_rules WHERE keyword = %s", (key_norm,))
            old_row = cur.fetchone()
            old_data = {"is_active": bool(old_row[0]) if old_row else None}
            cur.execute(
                """
                INSERT INTO escalation_rules(keyword, is_active)
                VALUES (%s, %s)
                ON CONFLICT (keyword) DO UPDATE SET is_active = EXCLUDED.is_active
                """,
                (key_norm, is_active),
            )
            self._audit(cur, "escalation_rules", key_norm, old_data, {"is_active": is_active})

    def list_product_classes(self, query: str = "") -> list[dict[str, Any]]:
        sql = "SELECT code, price_from, is_active FROM product_classes"
        params: list[Any] = []
        if query.strip():
            sql += " WHERE code ILIKE %s"
            params.append(f"%{query.strip()}%")
        sql += " ORDER BY code ASC"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            {"code": str(code), "price_from": float(price), "is_active": bool(active)}
            for code, price, active in rows
        ]

    def upsert_product_class(self, code: str, price_from: float, *, is_active: bool = True) -> None:
        code_norm = code.lower().strip()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT price_from, is_active FROM product_classes WHERE code = %s",
                (code_norm,),
            )
            old_row = cur.fetchone()
            old_data = {
                "price_from": float(old_row[0]) if old_row else None,
                "is_active": bool(old_row[1]) if old_row else None,
            }
            cur.execute(
                """
                INSERT INTO product_classes(code, price_from, is_active)
                VALUES (%s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                SET price_from = EXCLUDED.price_from, is_active = EXCLUDED.is_active
                """,
                (code_norm, price_from, is_active),
            )
            self._audit(
                cur,
                "product_classes",
                code_norm,
                old_data,
                {"price_from": price_from, "is_active": is_active},
            )

    def list_countertops(self, query: str = "") -> list[dict[str, Any]]:
        sql = "SELECT code, price_from, is_active FROM countertop_materials"
        params: list[Any] = []
        if query.strip():
            sql += " WHERE code ILIKE %s"
            params.append(f"%{query.strip()}%")
        sql += " ORDER BY code ASC"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            {"code": str(code), "price_from": float(price), "is_active": bool(active)}
            for code, price, active in rows
        ]

    def upsert_countertop(self, code: str, price_from: float, *, is_active: bool = True) -> None:
        code_norm = code.lower().strip()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT price_from, is_active FROM countertop_materials WHERE code = %s",
                (code_norm,),
            )
            old_row = cur.fetchone()
            old_data = {
                "price_from": float(old_row[0]) if old_row else None,
                "is_active": bool(old_row[1]) if old_row else None,
            }
            cur.execute(
                """
                INSERT INTO countertop_materials(code, price_from, is_active)
                VALUES (%s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                SET price_from = EXCLUDED.price_from, is_active = EXCLUDED.is_active
                """,
                (code_norm, price_from, is_active),
            )
            self._audit(
                cur,
                "countertop_materials",
                code_norm,
                old_data,
                {"price_from": price_from, "is_active": is_active},
            )

    def list_service_fees(self) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT code, value, is_active FROM service_fees ORDER BY code ASC"
            )
            rows = cur.fetchall()
        return [
            {
                "code": str(code),
                "value": float(value),
                "label": FEE_LABELS.get(str(code), str(code)),
                "is_active": bool(active),
            }
            for code, value, active in rows
        ]

    def upsert_service_fee(self, code: str, value: float, *, is_active: bool = True) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT value, is_active FROM service_fees WHERE code = %s", (code,))
            old_row = cur.fetchone()
            old_data = {
                "value": float(old_row[0]) if old_row else None,
                "is_active": bool(old_row[1]) if old_row else None,
            }
            cur.execute(
                """
                INSERT INTO service_fees(code, value, is_active)
                VALUES (%s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                SET value = EXCLUDED.value, is_active = EXCLUDED.is_active
                """,
                (code, value, is_active),
            )
            self._audit(cur, "service_fees", code, old_data, {"value": value, "is_active": is_active})

    def list_catalog(
        self,
        category: str,
        *,
        query: str = "",
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT id, category, code, title, description, price_from,
                   image_width, image_height, is_active, sort_order,
                   updated_at, (image_thumb IS NOT NULL) AS has_image
            FROM catalog_items
            WHERE category = %s
        """
        params: list[Any] = [category]
        if query.strip():
            sql += " AND (code ILIKE %s OR title ILIKE %s OR description ILIKE %s)"
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern])
        if active_only:
            sql += " AND is_active = TRUE"
        sql += " ORDER BY sort_order ASC, title ASC"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            self._catalog_list_row(row)
            for row in rows
        ]

    def _catalog_list_row(self, row: tuple[Any, ...]) -> dict[str, Any]:
        item_id = int(row[0])
        has_image = bool(row[11])
        return {
            "id": item_id,
            "category": str(row[1]),
            "code": str(row[2]),
            "title": str(row[3]),
            "description": str(row[4]),
            "price_from": float(row[5]) if row[5] is not None else None,
            "image_path": catalog_media_path(item_id, "master") if has_image else None,
            "image_thumb_path": catalog_media_path(item_id, "thumb") if has_image else None,
            "image_width": int(row[6]) if row[6] is not None else None,
            "image_height": int(row[7]) if row[7] is not None else None,
            "is_active": bool(row[8]),
            "sort_order": int(row[9]),
            "updated_at": row[10].isoformat() if row[10] else None,
            "has_image": has_image,
        }

    def get_catalog_item(self, item_id: int) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, category, code, title, description, price_from,
                       image_width, image_height, is_active, sort_order,
                       (image_thumb IS NOT NULL) AS has_image
                FROM catalog_items
                WHERE id = %s
                """,
                (item_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        item_id_val = int(row[0])
        has_image = bool(row[10])
        return {
            "id": item_id_val,
            "category": str(row[1]),
            "code": str(row[2]),
            "title": str(row[3]),
            "description": str(row[4]),
            "price_from": float(row[5]) if row[5] is not None else None,
            "image_path": catalog_media_path(item_id_val, "master") if has_image else None,
            "image_thumb_path": catalog_media_path(item_id_val, "thumb") if has_image else None,
            "image_width": int(row[6]) if row[6] is not None else None,
            "image_height": int(row[7]) if row[7] is not None else None,
            "is_active": bool(row[8]),
            "sort_order": int(row[9]),
            "has_image": has_image,
        }

    def get_catalog_image_bytes(self, item_id: int, size: str = "thumb") -> bytes | None:
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

    def upsert_catalog_item(
        self,
        *,
        item_id: int | None,
        category: str,
        code: str,
        title: str,
        description: str,
        price_from: float | None,
        is_active: bool,
        sort_order: int,
        image_path: str | None = None,
    ) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            if item_id:
                cur.execute(
                    """
                    SELECT category, code, title, description, price_from, image_path, is_active, sort_order
                    FROM catalog_items WHERE id = %s
                    """,
                    (item_id,),
                )
                old_row = cur.fetchone()
                old_data = {
                    "category": old_row[0],
                    "code": old_row[1],
                    "title": old_row[2],
                    "description": old_row[3],
                    "price_from": float(old_row[4]) if old_row[4] is not None else None,
                    "image_path": old_row[5],
                    "is_active": bool(old_row[6]),
                    "sort_order": int(old_row[7]),
                } if old_row else {}
                new_image = image_path if image_path is not None else old_data.get("image_path")
                cur.execute(
                    """
                    UPDATE catalog_items
                    SET category = %s, code = %s, title = %s, description = %s,
                        price_from = %s, image_path = %s, is_active = %s, sort_order = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        category,
                        code.lower().strip(),
                        title.strip(),
                        description.strip(),
                        price_from,
                        new_image,
                        is_active,
                        sort_order,
                        item_id,
                    ),
                )
                row = cur.fetchone()
                new_data = {
                    "category": category,
                    "code": code.lower().strip(),
                    "title": title.strip(),
                    "description": description.strip(),
                    "price_from": price_from,
                    "image_path": new_image,
                    "is_active": is_active,
                    "sort_order": sort_order,
                }
                self._audit(cur, "catalog_items", str(item_id), old_data, new_data)
                return int(row[0])

            cur.execute(
                """
                INSERT INTO catalog_items(
                    category, code, title, description, price_from, image_path, is_active, sort_order
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    category,
                    code.lower().strip(),
                    title.strip(),
                    description.strip(),
                    price_from,
                    image_path,
                    is_active,
                    sort_order,
                ),
            )
            row = cur.fetchone()
            new_id = int(row[0])
            self._audit(
                cur,
                "catalog_items",
                str(new_id),
                {},
                {
                    "category": category,
                    "code": code.lower().strip(),
                    "title": title.strip(),
                    "description": description.strip(),
                    "price_from": price_from,
                    "image_path": image_path,
                    "is_active": is_active,
                    "sort_order": sort_order,
                },
            )
            return new_id

    def set_catalog_image(
        self,
        item_id: int,
        *,
        image_master: bytes,
        image_thumb: bytes,
        image_width: int,
        image_height: int,
    ) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT image_path, image_thumb_path, image_width, image_height, telegram_file_id
                FROM catalog_items WHERE id = %s
                """,
                (item_id,),
            )
            old_row = cur.fetchone()
            old_data = {
                "image_path": old_row[0] if old_row else None,
                "image_thumb_path": old_row[1] if old_row else None,
                "image_width": old_row[2] if old_row else None,
                "image_height": old_row[3] if old_row else None,
                "telegram_file_id": old_row[4] if old_row else None,
            }
            cur.execute(
                """
                UPDATE catalog_items
                SET image_master = %s,
                    image_thumb = %s,
                    image_path = %s,
                    image_thumb_path = %s,
                    image_width = %s,
                    image_height = %s,
                    telegram_file_id = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    image_master,
                    image_thumb,
                    catalog_media_path(item_id, "master"),
                    catalog_media_path(item_id, "thumb"),
                    image_width,
                    image_height,
                    item_id,
                ),
            )
            new_data = {
                "image_path": catalog_media_path(item_id, "master"),
                "image_thumb_path": catalog_media_path(item_id, "thumb"),
                "image_width": image_width,
                "image_height": image_height,
                "telegram_file_id": None,
                "image_bytes": True,
            }
            self._audit(cur, "catalog_items", str(item_id), old_data, new_data)

    def list_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT entity, entity_key, old_json, new_json, created_at
                FROM config_change_log
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (max(1, min(limit, 200)),),
            )
            rows = cur.fetchall()
        return [
            {
                "entity": str(entity),
                "entity_key": str(entity_key),
                "old": old_json,
                "new": new_json,
                "created_at": created_at.isoformat() if created_at else None,
            }
            for entity, entity_key, old_json, new_json, created_at in rows
        ]

    def _catalog_titles(self, cur: psycopg.Cursor, codes: dict[str, str | None]) -> dict[str, str | None]:
        titles: dict[str, str | None] = {}
        for category, code in codes.items():
            if not code:
                titles[category] = None
                continue
            cur.execute(
                "SELECT title FROM catalog_items WHERE category = %s AND code = %s LIMIT 1",
                (category, code),
            )
            row = cur.fetchone()
            titles[category] = str(row[0]) if row else None
        return titles

    def _order_row_to_dict(self, row: tuple[Any, ...], titles: dict[str, str | None]) -> dict[str, Any]:
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

    def list_orders(self, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        sql = """
            SELECT o.id, o.status, o.style_code, o.facade_code, o.countertop_code, o.hardware_code,
                   o.length_m, o.shape, o.phone, o.name, o.estimate_total, o.created_at,
                   o.lead_id, l.user_id, l.username, l.full_name
            FROM orders o
            JOIN leads l ON l.id = o.lead_id
        """
        params: list[Any] = []
        q = query.strip()
        if q:
            sql += """
            WHERE CAST(o.id AS TEXT) ILIKE %s
               OR o.phone ILIKE %s
               OR COALESCE(o.name, '') ILIKE %s
               OR CAST(l.user_id AS TEXT) ILIKE %s
            """
            pattern = f"%{q}%"
            params.extend([pattern, pattern, pattern, pattern])
        sql += " ORDER BY o.created_at DESC LIMIT %s"
        params.append(max(1, min(limit, 200)))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                titles = self._catalog_titles(
                    cur,
                    {
                        "style": row[2],
                        "facade": row[3],
                        "countertop": row[4],
                        "hardware": row[5],
                    },
                )
                result.append(self._order_row_to_dict(row, titles))
        return result

    def get_order(self, order_id: int) -> dict[str, Any] | None:
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
            titles = self._catalog_titles(
                cur,
                {
                    "style": row[2],
                    "facade": row[3],
                    "countertop": row[4],
                    "hardware": row[5],
                },
            )
            return self._order_row_to_dict(row, titles)

    def list_order_dialogs(self, order_id: int, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT lead_id FROM orders WHERE id = %s", (order_id,))
            row = cur.fetchone()
            if not row:
                return []
            lead_id = int(row[0])
            cur.execute(
                """
                SELECT source, text, created_at
                FROM dialogs
                WHERE lead_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (lead_id, max(1, min(limit, 500))),
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

    def list_escalation_cases(
        self,
        *,
        query: str = "",
        kind: str = "",
        has_order: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        from src.bot.escalation_cases import KIND_LABELS

        sql = """
            SELECT id, kind, summary, order_id, manager_name, phone, full_name, username,
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
        return [
            {
                "id": int(row[0]),
                "kind": str(row[1]),
                "kind_label": KIND_LABELS.get(str(row[1]), str(row[1])),
                "summary": str(row[2] or ""),
                "order_id": int(row[3]) if row[3] is not None else None,
                "manager_name": row[4],
                "phone": row[5],
                "full_name": row[6],
                "username": row[7],
                "user_id": int(row[8]),
                "status": str(row[9]),
                "created_at": row[10].isoformat() if row[10] else None,
            }
            for row in rows
        ]

    def get_escalation_case(self, case_id: int) -> dict[str, Any] | None:
        from src.bot.escalation_cases import KIND_LABELS

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
            "kind_label": KIND_LABELS.get(str(row[1]), str(row[1])),
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
