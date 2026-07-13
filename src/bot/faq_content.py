from __future__ import annotations

import re
from typing import Any, Callable

TIMEZONE_DEFAULT_CITY: dict[str, str] = {
    "Asia/Irkutsk": "Иркутск",
    "Asia/Krasnoyarsk": "Красноярск",
    "Asia/Novosibirsk": "Новосибирск",
    "Asia/Yekaterinburg": "Екатеринбург",
    "Europe/Moscow": "Москва",
    "UTC": "Иркутск",
}

CITY_DATIVE: dict[str, str] = {
    "Иркутск": "Иркутску",
    "Красноярск": "Красноярску",
    "Новосибирск": "Новосибирску",
    "Екатеринбург": "Екатеринбургу",
    "Москва": "Москве",
}

_WORD_RE = re.compile(r"[а-яёa-z0-9']+", re.IGNORECASE)

# Частые русские окончания (длинные первыми) — эвристика, без словаря синонимов.
_RUSSIAN_SUFFIXES: tuple[str, ...] = (
    "иями",
    "ями",
    "ами",
    "ого",
    "ему",
    "ому",
    "ими",
    "ией",
    "ием",
    "ов",
    "ев",
    "ёв",
    "ам",
    "ям",
    "ах",
    "ях",
    "ом",
    "ем",
    "ой",
    "ей",
    "ий",
    "ый",
    "ая",
    "ое",
    "ие",
    "ые",
    "ию",
    "ью",
    "ия",
    "ья",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "и",
    "ы",
    "о",
    "ь",
)


def _format_money(value: float | int) -> str:
    return f"{int(value):,}".replace(",", " ")


def normalize_text(text: str) -> str:
    return text.lower().replace("ё", "е").strip()


def tokenize_words(text: str) -> list[str]:
    return _WORD_RE.findall(normalize_text(text))


def russian_stem(word: str, *, min_stem: int = 4) -> str:
    w = normalize_text(word)
    if len(w) <= min_stem:
        return w
    for _ in range(5):
        if len(w) <= min_stem:
            break
        stripped = False
        for suffix in _RUSSIAN_SUFFIXES:
            if len(w) - len(suffix) >= min_stem and w.endswith(suffix):
                w = w[: -len(suffix)]
                stripped = True
                break
        if not stripped:
            break
    return w


def stems_compatible(left: str, right: str, *, min_overlap: int = 4) -> bool:
    a = russian_stem(left)
    b = russian_stem(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return min(len(a), len(b)) >= min_overlap
    overlap = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        overlap += 1
    return overlap >= min_overlap


def faq_key_matches(key: str, text: str) -> bool:
    key_norm = normalize_text(key)
    text_norm = normalize_text(text)
    if not key_norm:
        return False
    if key_norm in text_norm:
        return True

    key_tokens = tokenize_words(key_norm)
    text_tokens = tokenize_words(text_norm)
    if not key_tokens or not text_tokens:
        return False

    if len(key_tokens) == 1:
        token = key_tokens[0]
        min_overlap = 3 if len(token) <= 4 else 4
        return any(stems_compatible(token, word, min_overlap=min_overlap) for word in text_tokens)

    return all(
        any(stems_compatible(key_token, word) for word in text_tokens) for key_token in key_tokens
    )


def pick_faq_key(text: str, keys: list[str]) -> str | None:
    unique = sorted({normalize_text(key) for key in keys if key and key.strip()}, key=len, reverse=True)
    for key in unique:
        if faq_key_matches(key, text):
            return key
    return None


def resolve_faq_item(
    text: str,
    items: list[tuple[str, str]],
    *,
    special_answers: dict[str, Callable[[], str]] | None = None,
) -> tuple[str, str] | None:
    keys = [str(key) for key, _ in items if key]
    matched = pick_faq_key(text, keys)
    if not matched:
        return None
    if special_answers and matched in special_answers:
        return matched, special_answers[matched]()
    for key, answer in items:
        if normalize_text(str(key)) == matched:
            return matched, str(answer)
    return None


def city_in_prepositional(city: str) -> str:
    name = city.strip()
    if not name:
        return "городу"
    if name in CITY_DATIVE:
        return CITY_DATIVE[name]
    if name.endswith("ск"):
        return f"{name}у"
    if name.endswith("а"):
        return f"{name[:-1]}е"
    return name


def resolve_brand_city(*, brand_city: str | None, timezone: str | None) -> str:
    if brand_city and brand_city.strip():
        return brand_city.strip()
    if timezone and timezone in TIMEZONE_DEFAULT_CITY:
        return TIMEZONE_DEFAULT_CITY[timezone]
    return "Иркутск"


def build_delivery_faq_answer(*, city: str, service_fees: dict[str, Any]) -> str:
    threshold = float(service_fees.get("delivery_city_free_threshold", 150_000))
    city_fixed = float(service_fees.get("delivery_city_fixed", 3_000))
    outside_base = float(service_fees.get("delivery_outside_base", 5_000))
    per_km = float(service_fees.get("delivery_outside_per_km", 50))
    city_in = city_in_prepositional(city)
    return (
        f"По {city_in} бесплатно от {_format_money(threshold)} ₽, иначе {_format_money(city_fixed)} ₽. "
        f"За город: от {_format_money(outside_base)} ₽ + {_format_money(per_km)} ₽/км."
    )


def format_friendly_faq_reply(answer: str, *, faq_key: str | None = None) -> str:
    if faq_key:
        label = faq_key.strip().capitalize()
        return f"Конечно, подскажу.\n\n{label}: {answer}"
    return f"Конечно, подскажу.\n\n{answer}"


QA_CONTINUE_BRIDGE = (
    "Если появятся ещё вопросы — спрашивайте, с удовольствием отвечу. "
    "Когда будете готовы, продолжим подбор кухни."
)

IDLE_AFTER_FAQ_HINT = "Можете задать ещё вопрос или начать подбор кнопкой ниже."
