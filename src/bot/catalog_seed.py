from __future__ import annotations

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

CATALOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS catalog_items (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price_from NUMERIC(12, 2),
    image_path TEXT,
    image_thumb_path TEXT,
    image_master BYTEA,
    image_thumb BYTEA,
    image_width INT,
    image_height INT,
    telegram_file_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(category, code)
);

CREATE INDEX IF NOT EXISTS idx_catalog_items_category_active
    ON catalog_items(category, is_active, sort_order);

ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS image_master BYTEA;
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS image_thumb BYTEA;
"""

ORDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'new',
    style_code TEXT,
    facade_code TEXT,
    countertop_code TEXT,
    hardware_code TEXT,
    length_m NUMERIC(6, 2),
    shape TEXT,
    phone TEXT,
    name TEXT,
    estimate_total NUMERIC(12, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_status_created_at ON orders(status, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_lead_id ON orders(lead_id);
"""
