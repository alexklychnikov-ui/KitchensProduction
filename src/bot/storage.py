from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Protocol

from .catalog_seed import CATALOG_SEED
from .escalation_cases import funnel_snapshot_has_value
from .faq_content import build_delivery_faq_answer, resolve_faq_item, resolve_brand_city
from .funnel import WIZARD_STAGES
from .managers_config import DEFAULT_MANAGERS_CONFIG, ManagersConfig


def _seed_catalog_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, (category, code, title, description, price_from, sort_order) in enumerate(CATALOG_SEED, start=1):
        items.append(
            {
                "id": index,
                "category": category,
                "code": code,
                "title": title,
                "description": description,
                "price_from": float(price_from),
                "image_path": None,
                "image_thumb_path": None,
                "telegram_file_id": None,
                "is_active": True,
                "sort_order": sort_order,
            }
        )
    return items


class StorageBackend(Protocol):
    def add_event(self, user_id: int, event_type: str, payload: dict[str, Any]) -> None: ...
    def add_request(self, user_id: int, text: str, source: str) -> None: ...
    def ensure_lead_profile(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        username: str | None = None,
    ) -> None: ...
    def get_faq_answer(self, text: str) -> str | None: ...
    def get_faq_match(self, text: str) -> tuple[str, str] | None: ...
    def get_escalation_keywords(self) -> list[str]: ...
    def get_pricing_reference(self) -> dict[str, Any]: ...
    def get_user_message_count(self, user_id: int) -> int: ...
    def get_bot_message_count(self, user_id: int) -> int: ...
    def get_session_user_message_count(self, user_id: int) -> int: ...
    def get_session_bot_message_count(self, user_id: int) -> int: ...
    def get_voice_retry_count(self, user_id: int) -> int: ...
    def increment_voice_retry_count(self, user_id: int) -> int: ...
    def reset_voice_retry_count(self, user_id: int) -> None: ...
    def admin_set_faq(self, actor_user_id: int, key: str, answer: str) -> None: ...
    def admin_set_escalation_keyword(self, actor_user_id: int, keyword: str, is_active: bool) -> None: ...
    def admin_set_service_fee(self, actor_user_id: int, code: str, value: float) -> None: ...
    def admin_list_faq(self) -> list[tuple[str, str]]: ...
    def admin_get_faq(self, key: str) -> str | None: ...
    def admin_list_escalation_rules(self) -> list[tuple[str, bool]]: ...
    def admin_list_service_fees(self) -> list[tuple[str, float]]: ...
    def get_funnel_state(self, user_id: int) -> dict[str, Any]: ...
    def set_funnel_state(self, user_id: int, state: dict[str, Any]) -> None: ...
    def clear_funnel_state(self, user_id: int) -> None: ...
    def list_catalog(self, category: str) -> list[dict[str, Any]]: ...
    def get_catalog_item(self, category: str, code: str) -> dict[str, Any] | None: ...
    def get_catalog_image_bytes(self, item_id: int, size: str = "master") -> bytes | None: ...
    def set_catalog_telegram_file_id(self, item_id: int, file_id: str) -> None: ...
    def create_order(self, user_id: int, payload: dict[str, Any]) -> int: ...
    def admin_list_orders(self, limit: int = 10) -> list[dict[str, Any]]: ...
    def admin_get_order(self, order_id: int) -> dict[str, Any] | None: ...
    def admin_list_order_dialogs(self, order_id: int, limit: int = 30) -> list[dict[str, Any]]: ...
    def get_timezone(self) -> str: ...
    def get_brand_name(self) -> str: ...
    def get_managers_config(self) -> ManagersConfig: ...
    def list_stale_funnel_sessions(self, *, timeout_minutes: int) -> list[dict[str, Any]]: ...
    def mark_funnel_abandoned_escalated(self, user_id: int) -> None: ...
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
    ) -> int: ...
    def admin_list_escalation_cases(
        self,
        *,
        query: str = "",
        kind: str = "",
        has_order: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...
    def admin_get_escalation_case(self, case_id: int) -> dict[str, Any] | None: ...


@dataclass
class InMemoryStorage:
    events: list[dict[str, Any]] = field(default_factory=list)
    requests: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)
    faq_responses: dict[str, str] = field(
        default_factory=lambda: {
            "цена": "Ориентировочную стоимость можем подсказать после базовых параметров. Напишите размеры и желаемый стиль кухни.",
            "срок": "Обычно срок изготовления кухни 3-6 недель, зависит от материалов и сложности.",
            "материал": "Работаем с ЛДСП, МДФ и шпоном. Подскажем оптимальный вариант под ваш бюджет.",
            "доставка": "Есть доставка и установка. Уточним детали по вашему адресу.",
            "гарантия": "Гарантия: 24 месяца на корпус/фасады, 12 месяцев на фурнитуру и механизмы.",
        }
    )
    escalation_rules: dict[str, bool] = field(
        default_factory=lambda: {
            "менеджер": True,
            "человек": True,
            "оператор": True,
            "жалоба": True,
            "претенз": True,
            "точный расчет": True,
            "точный расчёт": True,
            "договор": True,
            "замер": True,
            "замерщик": True,
            "заказать": True,
            "рассчитать точно": True,
            "оплатить": True,
            "брак": True,
            "вернуть деньги": True,
            "директор": True,
        }
    )
    pricing_reference: dict[str, Any] = field(
        default_factory=lambda: {
            "product_classes": {
                "эконом": 25000.0,
                "стандарт": 38000.0,
                "премиум": 55000.0,
            },
            "countertops": {
                "лдсп": 2500.0,
                "акрил": 9000.0,
                "кварц": 14000.0,
                "массив": 18000.0,
            },
            "service_fees": {
                "delivery_city_free_threshold": 150000.0,
                "delivery_city_fixed": 3000.0,
                "delivery_outside_base": 5000.0,
                "delivery_outside_per_km": 50.0,
                "assembly_percent": 0.15,
                "assembly_min": 12000.0,
            },
        }
    )
    voice_retry_count: dict[int, int] = field(default_factory=dict)
    funnel_states: dict[int, dict[str, Any]] = field(default_factory=dict)
    catalog_items: list[dict[str, Any]] = field(default_factory=_seed_catalog_items)
    catalog_image_bytes: dict[int, dict[str, bytes]] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)
    _next_order_id: int = 1
    brand_city: str = "Иркутск"
    timezone: str = "Asia/Irkutsk"
    brand_name: str = "АртКухня"
    managers_config: ManagersConfig = field(default_factory=lambda: DEFAULT_MANAGERS_CONFIG)
    funnel_watch: dict[int, dict[str, Any]] = field(default_factory=dict)
    escalation_cases: list[dict[str, Any]] = field(default_factory=list)
    _next_escalation_id: int = 1
    lead_profiles: dict[int, dict[str, str | None]] = field(default_factory=dict)

    def ensure_lead_profile(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        username: str | None = None,
    ) -> None:
        profile = self.lead_profiles.setdefault(user_id, {"full_name": None, "username": None})
        if full_name and full_name.strip():
            profile["full_name"] = full_name.strip()
        if username and username.strip():
            profile["username"] = username.strip().lstrip("@")
        if user_id in self.funnel_watch:
            self.funnel_watch[user_id]["full_name"] = profile.get("full_name")
            self.funnel_watch[user_id]["username"] = profile.get("username")

    def add_event(self, user_id: int, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "event_type": event_type,
            "payload": payload,
        }
        with self._lock:
            self.events.append(event)

    def add_request(self, user_id: int, text: str, source: str) -> None:
        item = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "source": source,
        }
        with self._lock:
            self.requests.setdefault(user_id, []).append(item)

    def get_faq_match(self, text: str) -> tuple[str, str] | None:
        items = [(key, value) for key, value in self.faq_responses.items()]

        def delivery_answer() -> str:
            city = resolve_brand_city(brand_city=self.brand_city, timezone=self.timezone)
            fees = self.get_pricing_reference().get("service_fees", {})
            return build_delivery_faq_answer(city=city, service_fees=fees)

        return resolve_faq_item(text, items, special_answers={"доставка": delivery_answer})

    def get_faq_answer(self, text: str) -> str | None:
        match = self.get_faq_match(text)
        return match[1] if match else None

    def get_escalation_keywords(self) -> list[str]:
        return [keyword for keyword, active in self.escalation_rules.items() if active]

    def get_pricing_reference(self) -> dict[str, Any]:
        return self.pricing_reference

    def get_user_message_count(self, user_id: int) -> int:
        return len(self.requests.get(user_id, []))

    def get_bot_message_count(self, user_id: int) -> int:
        count = 0
        for event in self.events:
            if event.get("user_id") == user_id and event.get("event_type") == "bot_reply":
                count += 1
        return count

    def _session_start_iso(self, user_id: int) -> str | None:
        for event in reversed(self.events):
            if event.get("user_id") == user_id and event.get("event_type") == "session_start":
                return event.get("timestamp")
        return None

    def get_session_user_message_count(self, user_id: int) -> int:
        session_ts = self._session_start_iso(user_id)
        items = self.requests.get(user_id, [])
        if not session_ts:
            return len(items)
        return sum(1 for item in items if item.get("timestamp", "") >= session_ts)

    def get_session_bot_message_count(self, user_id: int) -> int:
        session_ts = self._session_start_iso(user_id)
        count = 0
        for event in self.events:
            if event.get("user_id") != user_id or event.get("event_type") != "bot_reply":
                continue
            if session_ts and event.get("timestamp", "") < session_ts:
                continue
            count += 1
        return count

    def get_voice_retry_count(self, user_id: int) -> int:
        return self.voice_retry_count.get(user_id, 0)

    def increment_voice_retry_count(self, user_id: int) -> int:
        value = self.voice_retry_count.get(user_id, 0) + 1
        self.voice_retry_count[user_id] = value
        return value

    def reset_voice_retry_count(self, user_id: int) -> None:
        self.voice_retry_count[user_id] = 0

    def admin_set_faq(self, actor_user_id: int, key: str, answer: str) -> None:
        self.faq_responses[key.lower()] = answer

    def admin_set_escalation_keyword(self, actor_user_id: int, keyword: str, is_active: bool) -> None:
        self.escalation_rules[keyword.lower()] = is_active

    def admin_set_service_fee(self, actor_user_id: int, code: str, value: float) -> None:
        self.pricing_reference.setdefault("service_fees", {})[code] = value

    def admin_list_faq(self) -> list[tuple[str, str]]:
        return sorted(self.faq_responses.items(), key=lambda item: item[0])

    def admin_get_faq(self, key: str) -> str | None:
        return self.faq_responses.get(key.lower())

    def admin_list_escalation_rules(self) -> list[tuple[str, bool]]:
        return sorted(self.escalation_rules.items(), key=lambda item: item[0])

    def admin_list_service_fees(self) -> list[tuple[str, float]]:
        fees = self.pricing_reference.get("service_fees", {})
        return sorted(fees.items(), key=lambda item: item[0])

    def get_funnel_state(self, user_id: int) -> dict[str, Any]:
        return dict(self.funnel_states.get(user_id, {}))

    def set_funnel_state(self, user_id: int, state: dict[str, Any]) -> None:
        self.funnel_states[user_id] = dict(state)
        self.add_event(user_id, "funnel_state", state)
        stage = str(state.get("stage") or "idle")
        if stage in WIZARD_STAGES and stage != "done" and funnel_snapshot_has_value(state):
            self.funnel_watch[user_id] = {
                "user_id": user_id,
                "stage": stage,
                "state_json": dict(state),
                "updated_at": datetime.now(timezone.utc),
                "full_name": None,
                "username": None,
            }
        else:
            self.funnel_watch.pop(user_id, None)

    def clear_funnel_state(self, user_id: int) -> None:
        self.funnel_states.pop(user_id, None)
        self.funnel_watch.pop(user_id, None)
        self.add_event(user_id, "funnel_state", {})

    def list_catalog(self, category: str) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self.catalog_items
            if item["category"] == category and item.get("is_active", True)
        ]

    def get_catalog_item(self, category: str, code: str) -> dict[str, Any] | None:
        for item in self.catalog_items:
            if item["category"] == category and item["code"] == code and item.get("is_active", True):
                return dict(item)
        return None

    def set_catalog_telegram_file_id(self, item_id: int, file_id: str) -> None:
        for item in self.catalog_items:
            if item["id"] == item_id:
                item["telegram_file_id"] = file_id
                return

    def get_catalog_image_bytes(self, item_id: int, size: str = "master") -> bytes | None:
        payload = self.catalog_image_bytes.get(item_id)
        if not payload:
            return None
        return payload.get(size) or payload.get("master")

    def create_order(self, user_id: int, payload: dict[str, Any]) -> int:
        order_id = self._next_order_id
        self._next_order_id += 1
        record = {
            "id": order_id,
            "user_id": user_id,
            "status": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        self.orders.append(record)
        self.add_event(user_id, "order_created", {"order_id": order_id, **payload})
        return order_id

    def admin_list_orders(self, limit: int = 10) -> list[dict[str, Any]]:
        items = sorted(self.orders, key=lambda item: item.get("created_at", ""), reverse=True)
        return [dict(item) for item in items[:limit]]

    def admin_get_order(self, order_id: int) -> dict[str, Any] | None:
        for item in self.orders:
            if int(item.get("id", 0)) == order_id:
                return dict(item)
        return None

    def admin_list_order_dialogs(self, order_id: int, limit: int = 30) -> list[dict[str, Any]]:
        order = self.admin_get_order(order_id)
        if not order:
            return []
        user_id = int(order.get("user_id", 0))
        dialogs = [
            {
                "source": req.get("source", "text"),
                "text": req.get("text", ""),
                "created_at": req.get("timestamp"),
            }
            for req in self.requests.get(user_id, [])
        ]
        return dialogs[-limit:]

    def get_timezone(self) -> str:
        return self.timezone

    def get_brand_name(self) -> str:
        return self.brand_name

    def get_managers_config(self) -> ManagersConfig:
        return self.managers_config

    def list_stale_funnel_sessions(self, *, timeout_minutes: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        result: list[dict[str, Any]] = []
        for user_id, row in self.funnel_watch.items():
            updated = row.get("updated_at")
            if row.get("abandoned_escalated_at"):
                continue
            if isinstance(updated, str):
                updated_dt = datetime.fromisoformat(updated)
            else:
                updated_dt = updated
            if updated_dt <= cutoff:
                result.append(dict(row))
        return result

    def mark_funnel_abandoned_escalated(self, user_id: int) -> None:
        if user_id in self.funnel_watch:
            self.funnel_watch[user_id]["abandoned_escalated_at"] = datetime.now(timezone.utc).isoformat()

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
        case_id = self._next_escalation_id
        self._next_escalation_id += 1
        self.escalation_cases.append(
            {
                "id": case_id,
                "user_id": user_id,
                "kind": kind,
                "reasons": reasons,
                "summary": summary,
                "funnel_snapshot": funnel_snapshot or {},
                "order_id": order_id,
                "manager_id": manager_id,
                "manager_name": manager_name,
                "phone": phone,
                "full_name": full_name,
                "username": username,
                "status": "linked_order" if order_id else "new",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "notified_at": datetime.now(timezone.utc).isoformat() if notified else None,
            }
        )
        return case_id

    def admin_list_escalation_cases(
        self,
        *,
        query: str = "",
        kind: str = "",
        has_order: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        items = list(self.escalation_cases)
        if kind:
            items = [item for item in items if item.get("kind") == kind]
        if has_order == "yes":
            items = [item for item in items if item.get("order_id")]
        elif has_order == "no":
            items = [item for item in items if not item.get("order_id")]
        if query.strip():
            q = query.strip().lower()
            items = [
                item
                for item in items
                if q in str(item.get("summary", "")).lower()
                or q in str(item.get("phone", "")).lower()
                or q in str(item.get("user_id", ""))
            ]
        items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return items[:limit]

    def admin_get_escalation_case(self, case_id: int) -> dict[str, Any] | None:
        for item in self.escalation_cases:
            if int(item.get("id", 0)) == case_id:
                return dict(item)
        return None
