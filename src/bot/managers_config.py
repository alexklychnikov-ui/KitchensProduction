from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DayHours:
    start: int
    end: int

    def contains_hour(self, hour: float) -> bool:
        return self.start <= hour < self.end


@dataclass(frozen=True)
class OfficeHours:
    mon_fri: DayHours
    saturday: DayHours | None
    sunday: DayHours | None


@dataclass(frozen=True)
class ManagerProfile:
    id: str
    name: str
    short_name: str
    role: str
    routes: tuple[str, ...]
    phone: str
    telegram: str
    email: str
    schedule_label: str


@dataclass(frozen=True)
class StyleTemplates:
    greeting: str
    sales_handoff: str
    technical_handoff: str
    complaint_handoff: str
    uncertain_handoff: str


@dataclass(frozen=True)
class ManagersConfig:
    office_hours: OfficeHours
    managers: tuple[ManagerProfile, ...]
    duty_manager_id: str
    sla_minutes: int
    abandon_timeout_minutes: int
    style: StyleTemplates


MANAGERS_CONFIG_KEY = "managers_config"

DEFAULT_STYLE = StyleTemplates(
    greeting=(
        "Здравствуйте! Я бот студии «АртКухня» 🙂\n"
        "Помогу узнать про кухни на заказ — стоимость, сроки, материалы — "
        "или запишу вас на бесплатный замер. Что вас интересует?"
    ),
    sales_handoff=(
        "Отличный запрос, тут точно нужен индивидуальный расчёт! "
        "Уже передаю ваш вопрос менеджеру {name} — {pronoun} свяжется с вами в ближайшее время. 📐"
    ),
    technical_handoff=(
        "Такой вопрос лучше обсудить с нашим техническим менеджером {name} — "
        "{pronoun} подскажет точно и свяжется с вами."
    ),
    complaint_handoff=(
        "Мне жаль, что так получилось. Это важный вопрос, и я хочу, чтобы его решил человек, "
        "который сможет разобраться детально. Передаю обращение {name} — "
        "{pronoun} обязательно с вами свяжется."
    ),
    uncertain_handoff=(
        "Хм, здесь я не совсем уверен, чтобы не ввести вас в заблуждение. "
        "Давайте я подключу нашего менеджера {name} — {pronoun} ответит точно."
    ),
)

DEFAULT_MANAGERS_CONFIG = ManagersConfig(
    office_hours=OfficeHours(
        mon_fri=DayHours(9, 18),
        saturday=DayHours(9, 19),
        sunday=None,
    ),
    duty_manager_id="anna",
    sla_minutes=15,
    abandon_timeout_minutes=10,
    managers=(
        ManagerProfile(
            id="maria",
            name="Иванова Мария Сергеевна",
            short_name="Мария",
            role="Менеджер по продажам — новые заказы, расчёт, замер",
            routes=("sales",),
            phone="+7 (395) 271-40-15, доб. 101",
            telegram="@maria_kuhnidom",
            email="m.ivanova@artkuhnya-irk.ru",
            schedule_label="Пн–Пт, 9:00–18:00",
        ),
        ManagerProfile(
            id="dmitry",
            name="Петров Дмитрий Олегович",
            short_name="Дмитрий",
            role="Технический менеджер — замеры, монтаж, гарантия",
            routes=("technical",),
            phone="+7 (395) 271-40-15, доб. 102",
            telegram="@dmitry_kuhnidom",
            email="d.petrov@artkuhnya-irk.ru",
            schedule_label="Пн–Сб, 9:00–19:00",
        ),
        ManagerProfile(
            id="anna",
            name="Сергеева Анна Викторовна",
            short_name="Анна",
            role="Руководитель клиентского сервиса — жалобы, срочные и внерабочие обращения",
            routes=("duty",),
            phone="+7 (964) 350-22-17",
            telegram="@anna_kuhnidom",
            email="a.sergeeva@artkuhnya-irk.ru",
            schedule_label="Ежедневно, 8:00–21:00",
        ),
    ),
    style=DEFAULT_STYLE,
)

COMPLAINT_MARKERS = ("жалоб", "претенз", "брак", "вернуть", "директор", "недоволь")
TECHNICAL_MARKERS = ("монтаж", "гарант", "замерщик", "установк")
URGENT_MARKERS = ("срочно", "срочная", "urgent")


def _pronoun_for_name(short_name: str) -> str:
    return "она" if short_name.endswith(("а", "я")) else "он"


def managers_config_to_dict(config: ManagersConfig) -> dict[str, Any]:
    return {
        "office_hours": {
            "mon_fri": {"start": config.office_hours.mon_fri.start, "end": config.office_hours.mon_fri.end},
            "sat": (
                {"start": config.office_hours.saturday.start, "end": config.office_hours.saturday.end}
                if config.office_hours.saturday
                else None
            ),
            "sun": (
                {"start": config.office_hours.sunday.start, "end": config.office_hours.sunday.end}
                if config.office_hours.sunday
                else None
            ),
        },
        "duty_manager_id": config.duty_manager_id,
        "sla_minutes": config.sla_minutes,
        "abandon_timeout_minutes": config.abandon_timeout_minutes,
        "managers": [
            {
                "id": manager.id,
                "name": manager.name,
                "short_name": manager.short_name,
                "role": manager.role,
                "routes": list(manager.routes),
                "phone": manager.phone,
                "telegram": manager.telegram,
                "email": manager.email,
                "schedule_label": manager.schedule_label,
            }
            for manager in config.managers
        ],
        "style": {
            "greeting": config.style.greeting,
            "sales_handoff": config.style.sales_handoff,
            "technical_handoff": config.style.technical_handoff,
            "complaint_handoff": config.style.complaint_handoff,
            "uncertain_handoff": config.style.uncertain_handoff,
        },
    }


def managers_config_from_dict(data: dict[str, Any]) -> ManagersConfig:
    office = data.get("office_hours") or {}
    mon_fri = office.get("mon_fri") or {"start": 9, "end": 18}
    sat_raw = office.get("sat")
    sun_raw = office.get("sun")

    def _day_hours(raw: dict[str, Any] | None) -> DayHours | None:
        if not raw:
            return None
        return DayHours(int(raw.get("start", 9)), int(raw.get("end", 18)))

    style_raw = data.get("style") or {}
    style = StyleTemplates(
        greeting=str(style_raw.get("greeting") or DEFAULT_STYLE.greeting),
        sales_handoff=str(style_raw.get("sales_handoff") or DEFAULT_STYLE.sales_handoff),
        technical_handoff=str(style_raw.get("technical_handoff") or DEFAULT_STYLE.technical_handoff),
        complaint_handoff=str(style_raw.get("complaint_handoff") or DEFAULT_STYLE.complaint_handoff),
        uncertain_handoff=str(style_raw.get("uncertain_handoff") or DEFAULT_STYLE.uncertain_handoff),
    )

    managers: list[ManagerProfile] = []
    for raw in data.get("managers") or []:
        manager_id = str(raw.get("id") or "").strip()
        if not manager_id:
            continue
        routes = tuple(str(item).strip() for item in (raw.get("routes") or []) if str(item).strip())
        managers.append(
            ManagerProfile(
                id=manager_id,
                name=str(raw.get("name") or manager_id),
                short_name=str(raw.get("short_name") or raw.get("name") or manager_id),
                role=str(raw.get("role") or ""),
                routes=routes or ("sales",),
                phone=str(raw.get("phone") or ""),
                telegram=str(raw.get("telegram") or ""),
                email=str(raw.get("email") or ""),
                schedule_label=str(raw.get("schedule_label") or ""),
            )
        )

    if not managers:
        return DEFAULT_MANAGERS_CONFIG

    return ManagersConfig(
        office_hours=OfficeHours(
            mon_fri=DayHours(int(mon_fri.get("start", 9)), int(mon_fri.get("end", 18))),
            saturday=_day_hours(sat_raw if isinstance(sat_raw, dict) else None),
            sunday=_day_hours(sun_raw if isinstance(sun_raw, dict) else None),
        ),
        duty_manager_id=str(data.get("duty_manager_id") or "anna"),
        sla_minutes=int(data.get("sla_minutes") or 15),
        abandon_timeout_minutes=max(10, min(120, int(data.get("abandon_timeout_minutes") or 10))),
        managers=tuple(managers),
        style=style,
    )


def parse_managers_config(raw: str | None) -> ManagersConfig:
    if not raw or not raw.strip():
        return DEFAULT_MANAGERS_CONFIG
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_MANAGERS_CONFIG
    if not isinstance(data, dict):
        return DEFAULT_MANAGERS_CONFIG
    return managers_config_from_dict(data)


def serialize_managers_config(config: ManagersConfig) -> str:
    return json.dumps(managers_config_to_dict(config), ensure_ascii=False, indent=2)


def get_manager_by_id(config: ManagersConfig, manager_id: str) -> ManagerProfile | None:
    for manager in config.managers:
        if manager.id == manager_id:
            return manager
    return None


def get_manager_for_route(config: ManagersConfig, route: str) -> ManagerProfile:
    for manager in config.managers:
        if route in manager.routes:
            return manager
    duty = get_manager_by_id(config, config.duty_manager_id)
    if duty:
        return duty
    return config.managers[0]


def _text_has_any(text: str, markers: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(marker in normalized for marker in markers)


def classify_escalation_route(*, reasons: list[str], source_text: str, outside_hours: bool) -> str:
    if outside_hours or "stt_failed" in reasons:
        return "duty"
    if _text_has_any(source_text, URGENT_MARKERS):
        return "duty"
    if _text_has_any(source_text, COMPLAINT_MARKERS) or any(
        marker in " ".join(reasons) for marker in ("complaint", "жалоб")
    ):
        return "duty"
    if "order_created" in reasons or "manager_requested" in reasons:
        return "sales"
    if _text_has_any(source_text, TECHNICAL_MARKERS):
        return "technical"
    if "attachments" in reasons:
        return "sales"
    if "keyword_trigger" in reasons:
        if _text_has_any(source_text, TECHNICAL_MARKERS):
            return "technical"
        if _text_has_any(source_text, COMPLAINT_MARKERS):
            return "duty"
        return "sales"
    if "long_dialog" in reasons:
        return "sales"
    return "sales"


def resolve_manager(
    *,
    config: ManagersConfig,
    reasons: list[str],
    source_text: str,
    outside_hours: bool,
) -> ManagerProfile:
    route = classify_escalation_route(
        reasons=reasons,
        source_text=source_text,
        outside_hours=outside_hours,
    )
    if outside_hours and route != "duty":
        duty = get_manager_by_id(config, config.duty_manager_id)
        if duty:
            return duty
    return get_manager_for_route(config, route)


def build_client_escalation_message(
    *,
    manager: ManagerProfile,
    config: ManagersConfig,
    reasons: list[str],
    source_text: str,
    outside_hours: bool,
) -> str:
    route = classify_escalation_route(
        reasons=reasons,
        source_text=source_text,
        outside_hours=outside_hours,
    )
    pronoun = _pronoun_for_name(manager.short_name)
    if route == "duty" or _text_has_any(source_text, COMPLAINT_MARKERS):
        template = config.style.complaint_handoff
    elif route == "technical":
        template = config.style.technical_handoff
    elif "stt_failed" in reasons:
        template = config.style.uncertain_handoff
    else:
        template = config.style.sales_handoff
    return template.format(name=manager.short_name, pronoun=pronoun)


def build_manager_notification(
    *,
    manager: ManagerProfile,
    full_name: str,
    username: str,
    user_id: int,
    reasons: list[str],
    source_text: str,
    outside_hours: bool,
    urgent: bool,
) -> str:
    lines = [
        "Эскалация клиента",
        f"Ответственный: {manager.name} ({manager.role})",
        f"Контакты: {manager.phone} · {manager.telegram} · {manager.email}",
        f"График: {manager.schedule_label}",
        f"Пользователь: {full_name} ({username})",
        f"User ID: {user_id}",
        f"Причины: {', '.join(reasons)}",
    ]
    if urgent:
        lines.append("Пометка: СРОЧНО")
    if outside_hours:
        lines.append("Вне основного рабочего времени — ответить в начале следующего рабочего дня")
    lines.append(f"Сообщение: {source_text}")
    return "\n".join(lines)
