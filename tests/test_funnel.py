from __future__ import annotations

from src.bot.funnel import (
    FunnelState,
    answer_wizard_question,
    apply_catalog_pick,
    apply_shape_pick,
    build_carousel_caption,
    carousel_keyboard,
    confirm_estimate,
    filter_escalation_keywords,
    format_catalog_price_line,
    process_wizard_text,
    request_manager_contact,
    start_wizard,
    wants_to_start_order,
)
from src.catalog_media import catalog_media_path
from src.bot.pricing import detect_length
from src.bot.storage import InMemoryStorage


def _catalog_ctx(storage: InMemoryStorage) -> dict:
    return {
        "catalog_lookup": storage.list_catalog,
        "public_base_url": None,
        "uploads_dir": None,
    }


def _pick_ctx(storage: InMemoryStorage) -> dict:
    return {
        **_catalog_ctx(storage),
        "pricing_reference": storage.get_pricing_reference(),
    }


def _full_ctx(storage: InMemoryStorage) -> dict:
    return {
        **_pick_ctx(storage),
        "faq_lookup": storage.get_faq_answer,
    }


def test_filter_measurement_keywords() -> None:
    keywords = ["менеджер", "замер", "договор"]
    filtered = filter_escalation_keywords(keywords, "хочу записаться на замер")
    assert "замер" not in filtered
    assert "менеджер" in filtered


def test_wants_to_start_order() -> None:
    assert wants_to_start_order("хочу подобрать кухню") is True
    assert wants_to_start_order("привет") is False


def test_start_wizard_step_context_only() -> None:
    storage = InMemoryStorage()
    state, result = start_wizard(
        FunnelState(),
        catalog_lookup=storage.list_catalog,
        public_base_url=None,
        uploads_dir=None,
    )
    assert state.stage == "style"
    assert result.carousel_category == "style"
    assert result.carousel_items is not None
    assert len(result.carousel_items) == 3


def test_wizard_full_flow() -> None:
    storage = InMemoryStorage()
    ctx = _pick_ctx(storage)
    state = FunnelState()

    state, result = start_wizard(state, **_catalog_ctx(storage))
    assert state.stage == "style"
    assert result.carousel_category == "style"
    assert result.carousel_items is not None
    assert len(result.carousel_items) == 3

    style = storage.get_catalog_item("style", "modern_wood")
    assert style is not None
    state, result = apply_catalog_pick(state, "style", "modern_wood", style, **ctx)
    assert state.stage == "length"
    assert "Стиль" in result.text

    state, result = process_wizard_text("3.5 м", state, **ctx)
    assert state.stage == "shape"
    assert state.length_m == 3.5

    state, result = apply_shape_pick(state, "corner", **_catalog_ctx(storage))
    assert state.stage == "facade"
    assert state.shape == "Угловая"

    facade = storage.get_catalog_item("facade", "mdf_white")
    assert facade is not None
    state, result = apply_catalog_pick(state, "facade", "mdf_white", facade, **ctx)
    assert state.stage == "countertop"

    top = storage.get_catalog_item("countertop", "quartz")
    assert top is not None
    state, result = apply_catalog_pick(state, "countertop", "quartz", top, **ctx)
    assert state.stage == "hardware"

    hardware = storage.get_catalog_item("hardware", "blum")
    assert hardware is not None
    state, result = apply_catalog_pick(state, "hardware", "blum", hardware, **ctx)
    assert state.stage == "estimate"
    assert "Ориентир" in result.text
    assert state.estimate_total is not None

    state, result = confirm_estimate(state)
    assert state.stage == "phone"

    state, result = process_wizard_text("+7 964 123 45 67", state, **ctx)
    assert state.stage == "done"
    assert result.create_order is True
    assert result.should_escalate is True
    assert state.phone == "+79641234567"

    order_id = storage.create_order(1, result.order_payload or {})
    assert order_id == 1
    assert len(storage.orders) == 1


def test_detect_length_bare_number() -> None:
    assert detect_length("3", bare_number=True) == 3.0
    assert detect_length("3,5", bare_number=True) == 3.5
    assert detect_length("3.5 м", bare_number=True) == 3.5
    assert detect_length("привет", bare_number=True) is None


def test_wizard_length_plain_number() -> None:
    storage = InMemoryStorage()
    state = FunnelState(stage="length", style_code="modern_wood", style_title="Современный")
    state, result = process_wizard_text("3", state, **_full_ctx(storage))
    assert state.length_m == 3.0
    assert state.stage == "shape"


def test_wizard_invalid_length() -> None:
    storage = InMemoryStorage()
    state = FunnelState(stage="length")
    state, result = process_wizard_text("непонятно", state, **_full_ctx(storage))
    assert state.stage == "length"
    assert "3" in result.text


def test_start_wizard_has_catalog_carousel() -> None:
    storage = InMemoryStorage()
    _, result = start_wizard(FunnelState(), **_catalog_ctx(storage))
    assert result.carousel_category == "style"
    assert result.carousel_items is not None
    assert len(result.carousel_items) == 3
    assert result.carousel_index == 0


def test_carousel_caption_shows_price() -> None:
    storage = InMemoryStorage()
    facade = storage.get_catalog_item("facade", "mdf_white")
    assert facade is not None
    caption = build_carousel_caption(
        facade,
        index=0,
        total=3,
        header="Выберите фасады",
    )
    assert "38 000" in caption
    assert "пог.м" in caption


def test_carousel_keyboard_select_shows_price() -> None:
    storage = InMemoryStorage()
    items = storage.list_catalog("facade")
    rows = carousel_keyboard("facade", items, 0)
    labels = [text for row in rows for text, _ in row]
    assert any("38 000" in label for label in labels)


def test_format_catalog_price_style_fallback() -> None:
    storage = InMemoryStorage()
    style = storage.get_catalog_item("style", "modern_wood")
    assert style is not None
    line = format_catalog_price_line(style)
    assert "фасад" in line.lower()


def test_catalog_media_path_format() -> None:
    assert catalog_media_path(3, "thumb").startswith("/catalog/media/")


def test_wizard_question_at_style_step() -> None:
    storage = InMemoryStorage()
    state = FunnelState(stage="style")
    _, result = process_wizard_text("это весь выбор фасадов?", state, **_full_ctx(storage))
    assert result.handled is True
    assert "фасады" in result.text.lower() or "шаг" in result.text.lower()
    assert result.carousel_category == "style"


def test_wizard_question_faq_and_hint() -> None:
    storage = InMemoryStorage()
    state = FunnelState(stage="facade", shape="Прямая", length_m=3.0, style_title="Скандинавский")
    _, result = answer_wizard_question("а сколько стоит доставка?", state, **_full_ctx(storage))
    assert result.handled is True
    assert "иркутск" in result.text.lower()
    assert result.carousel_category == "facade"


def test_manager_intent_requests_phone_at_estimate() -> None:
    storage = InMemoryStorage()
    state = FunnelState(
        stage="estimate",
        style_code="scandinavian",
        style_title="Скандинавский",
        length_m=3.0,
        shape="Прямая",
        facade_code="mdf_wood",
        facade_title="МДФ под дерево",
        countertop_code="ldsp",
        countertop_title="ЛДСП",
        hardware_code="blum",
        hardware_title="Blum",
        estimate_total=141172,
    )
    new_state, result = process_wizard_text("мне нужен человек", state, **_full_ctx(storage))
    assert new_state.stage == "phone"
    assert new_state.pending_manager is True
    assert "телефон" in result.text.lower()
    assert result.should_escalate is False

    new_state, result = process_wizard_text("+7 902 111 11 11", new_state, **_full_ctx(storage))
    assert new_state.phone == "+79021111111"
    assert result.should_escalate is True
    assert result.escalation_summary
    assert "Телефон" in result.escalation_summary
    assert result.create_order is True


def test_manager_intent_typo_operator() -> None:
    storage = InMemoryStorage()
    state = FunnelState(stage="estimate", estimate_total=100000, style_code="modern_wood", style_title="Современный")
    _, result = process_wizard_text("свяжите с опреатором", state, **_full_ctx(storage))
    assert result.text
    assert "телефон" in result.text.lower()
