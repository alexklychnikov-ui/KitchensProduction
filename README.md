# KitchensProduction — АртКухня

Telegram-бот + веб-админка для студии кухонь на заказ: воронка подбора с фото и ценами, заявки, FAQ, расчёт, STT, эскалация менеджеру.

**Прод:** [kitchen.alexklyvibe.ru](https://kitchen.alexklyvibe.ru) · бот `@Alex_KichenProduction_bot`

**Передача заказчику:** см. [`HANDOVER.md`](HANDOVER.md) — дамп БД, docker-compose, чеклист приёмки.

## Возможности

### Клиент (Telegram)

- Пошаговая воронка: стиль → длина → планировка → фасады → столешница → фурнитура → ориентир ₽ → телефон → заявка.
- Карусель каталога: одно фото, цена в подписи и на кнопке «Выбрать», навигация ◀️ ▶️.
- **Умные ответы в воронке** — бот понимает текущий шаг, отвечает на вопросы (FAQ, доставка, цена) и подсказывает, что делать дальше.
- **Запрос менеджера** — при «менеджер / оператор / человек» бот сначала просит телефон, потом эскалирует с конфигурацией воронки.
- FAQ, ориентировочный расчёт, голосовые (STT через ProxyAPI).
- Эскалация менеджеру по правилам + уведомление о новой заявке.

### Админка

- **Веб-дашборд** (`src/admin_web`): заявки, каталог с фото, прайс, FAQ, эскалация, настройки, аудит.
- **Telegram `/admin`**: последние заявки, сводка, ссылка на веб (FAQ/прайс/каталог — в дашборде).
- Фото каталога хранятся в PostgreSQL (`BYTEA`), отдаются по `/catalog/media/{id}/{size}.jpg`.

### Настройки и контент

- `app_settings`: `brand_name`, `brand_city`, `timezone` — город в ответах бота (доставка) и шапке дашборда.
- FAQ «доставка» **генерируется динамически**: город из `brand_city` (fallback — из часового пояса) + тарифы из `service_fees`.
- Прайс (`product_classes`, `countertops`, `service_fees`) общий для бота и дашборда.

### Данные

- PostgreSQL: `leads`, `dialogs`, `orders`, `catalog_items`, `faq_items`, `escalation_rules`, `app_settings`, …
- Каталог: 12 seed-позиций (стили, фасады, столешницы, фурнитура).
- `telegram_file_id` — кэш фото в Telegram после первой отправки.

## Стек

- Python 3.13+
- aiogram 3, FastAPI, uvicorn
- psycopg (PostgreSQL)
- Pillow (обработка фото каталога)
- openai SDK (STT)

## Структура

```
src/
  bot/
    main.py              — polling, выбор storage
    handlers.py          — сообщения, voice, escalation
    funnel.py            — воронка, карусель, Q&A, запрос менеджера
    funnel_handlers.py   — callbacks fn:start/pick/nav/confirm
    faq_content.py       — динамический FAQ доставки (город + тарифы)
    pricing.py           — расчёт по каталогу
    db_storage.py        — PostgreSQL
    admin_wizard.py      — /admin в Telegram
  admin_web/
    main.py              — uvicorn entry
    app.py               — API + дашборд
    repository.py        — доступ к БД
  catalog_media.py       — crop 4:3, BYTEA, URL медиа
scripts/
  migrate_catalog_files_to_db.py  — перенос фото с диска в БД
  deploy_admin_web.sh
  server_finish_deploy.sh
tests/                   — 68+ pytest
```

## ENV

Скопируйте `.env.example` → `.env`.

**Бот (обязательно):**

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен BotFather |
| `TELEGRAM_CHAT_ID` | Группа менеджеров |
| `PROXY_BASE_URL` | URL ProxyAPI/OpenAI |
| `OPENAI_MODEL_VOICE` | Модель STT, напр. `whisper-1` |
| `PROXY_API_KEY` | Ключ API (или `OPENAI_API_KEY`) |

**Продакшен + админка:**

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | PostgreSQL, напр. `postgresql://user:pass@127.0.0.1:5433/kitchens_bot` |
| `TELEGRAM_ADMIN_IDS` | CSV id админов |
| `ADMIN_DASHBOARD_USER` | Логин дашборда |
| `ADMIN_SESSION_SECRET` | Секрет сессии (≥32 символа) |
| `ADMIN_WEB_HOST` / `ADMIN_WEB_PORT` | Обычно `127.0.0.1:8081` |
| `CATALOG_PUBLIC_BASE_URL` | Публичный URL для фото в TG, напр. `https://kitchen.alexklyvibe.ru` |
| `ADMIN_DASHBOARD_URL` | Ссылка в `/admin` бота |

`ADMIN_UPLOADS_DIR` — опционально, только для legacy-миграции файлов с диска.

## Быстрый старт (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# заполнить .env
python -m src.bot.main          # бот
python -m src.admin_web.main    # дашборд → http://127.0.0.1:8081
```

Первый вход в дашборд: логин из `ADMIN_DASHBOARD_USER`, пароль **1111** (сменить в настройках).

## Тесты

```powershell
pytest tests/ -q
```

## Деплой (VPS)

Путь: `/opt/kitchens-bot`, systemd: `kitchens-bot.service`, `kitchens-admin.service`.

```bash
systemctl restart kitchens-bot.service kitchens-admin.service
python scripts/migrate_catalog_files_to_db.py   # один раз, если фото ещё на диске
```

## API дашборда (основное)

- `GET /api/orders` — список заявок
- `GET /api/orders/{id}` — заявка + диалог
- `GET /api/catalog/{category}` — каталог
- `POST /api/catalog/item/{id}/image` — загрузка фото → BYTEA
- `GET /catalog/media/{id}/thumb.jpg` — публичное превью (без auth)
- `GET/PUT /api/settings/{key}` — бренд, город, часовой пояс

## Callbacks воронки

| Callback | Действие |
|----------|----------|
| `fn:start` | Старт подбора |
| `fn:nav:{category}:{index}` | Карусель ◀️ ▶️ |
| `fn:pick:{category}:{code}` | Выбор позиции |
| `fn:confirm:estimate` | Запись на замер |

## Логика бота (кратко)

| Ситуация | Поведение |
|----------|-----------|
| Вопрос в воронке | `answer_wizard_question()` — контекст шага + FAQ + подсказка |
| «Менеджер» в воронке | Запрос телефона → эскалация с конфигурацией (+ заявка в БД) |
| FAQ «доставка» | Город из `brand_city` / timezone + суммы из прайса |
| Завершение воронки | `orders` + эскалация в группу |

## Примечания

- Без `DATABASE_URL` бот работает in-memory (без заявок и каталога в БД).
- Схема и seed создаются при старте (`ensure_schema_and_seed`).
- Daily report — каждые 24 ч после старта процесса (PostgreSQL).
