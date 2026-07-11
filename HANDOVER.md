# Передача проекта заказчику — АртКухня

Документ для сдачи проекта: исходный код, база с тестовыми данными, инструкции по запуску.

**Репозиторий:** https://github.com/alexklychnikov-ui/KitchensProduction  
**Руководство пользователя:** `READMEUser.md`  
**Техническая документация:** `README.md`

---

## 1. Состав пакета

| Артефакт | Назначение |
|----------|------------|
| Исходный код (`src/`, `scripts/`) | Бот + веб-админка |
| `delivery/kitchens_bot_handover.dump` | PostgreSQL с тестовыми данными (каталог, фото в BYTEA, заявки, FAQ, прайс) |
| `delivery/docker-compose.postgres.yml` | Postgres для локального/VPS запуска |
| `delivery/env.handover.example` | Шаблон `.env` без секретов |
| `scripts/restore_handover_db.ps1` | Восстановление БД (Windows) |
| `scripts/restore_handover_db.sh` | Восстановление БД (Linux) |
| `scripts/export_handover_db.sh` | Повторный экспорт БД с сервера |

### Что уже в дампе (на момент передачи)

| Таблица | Записей | Содержимое |
|---------|---------|------------|
| `catalog_items` | 12 | Стили, фасады, столешницы, фурнитура + фото в БД |
| `orders` | 2 | Тестовые заявки из воронки |
| `faq_items` | 5 | FAQ бота |
| `product_classes` | 3 | Классы кухонь |
| `countertop_materials` | 4 | Столешницы в прайсе |
| `service_fees` | 6 | Доставка, монтаж и др. |
| `escalation_rules` | 10 | Правила эскалации |
| `app_settings` | 4 | Бренд, город, часовой пояс, хэш пароля админки |
| `dialogs` | 37 | История тестовых диалогов |
| `leads` | 1 | Тестовый лид |
| `escalation_cases` | — | Журнал эскалаций (брошенная воронка, менеджер) |
| `funnel_watch` | — | Отслеживание незавершённых сессий воронки |

**Пароль дашборда после restore:** `1111` — сменить в **Настройки → Смена пароля**.

---

## 2. Быстрый старт у заказчика (Windows, локально)

### 2.1 Клонировать и окружение

```powershell
git clone https://github.com/alexklychnikov-ui/KitchensProduction.git
cd KitchensProduction
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2.2 Поднять Postgres и залить дамп

```powershell
.\scripts\restore_handover_db.ps1
```

### 2.3 Настроить `.env`

```powershell
copy delivery\env.handover.example .env
# заполнить TELEGRAM_*, PROXY_API_KEY, ADMIN_SESSION_SECRET, домены
```

### 2.4 Запуск

```powershell
python -m src.bot.main
python -m src.admin_web.main
```

Дашборд: http://127.0.0.1:8081 (логин `admin`, пароль `1111`).

### 2.5 Проверка

См. чеклист в разделе 5 ниже.

---

## 3. Деплой на VPS (Linux)

Путь по умолчанию: `/opt/kitchens-bot`.

### 3.1 Подготовка сервера

```bash
apt update && apt install -y python3-venv python3-pip docker.io docker-compose-plugin nginx
git clone https://github.com/alexklychnikov-ui/KitchensProduction.git /opt/kitchens-bot
cd /opt/kitchens-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3.2 База данных

```bash
bash scripts/restore_handover_db.sh
```

### 3.3 Конфиг

```bash
cp delivery/env.handover.example .env
nano .env   # токены, домен, секреты
```

### 3.4 Systemd + nginx

```bash
bash scripts/server_finish_deploy.sh   # kitchens-bot.service
bash scripts/deploy_admin_web.sh       # kitchens-admin.service + nginx
```

Конфиг nginx: `scripts/nginx-kitchen.alexklyvibe.ru.conf` (заменить домен + SSL через certbot).

---

## 4. Секреты — что заменить заказчику

| Переменная | Где взять |
|------------|-----------|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) — свой бот или передача текущего |
| `TELEGRAM_CHAT_ID` | ID группы менеджеров (добавить бота в группу) |
| `TELEGRAM_ADMIN_IDS` | Telegram user id владельца/админа |
| `PROXY_API_KEY` | [ProxyAPI](https://proxyapi.ru) — для распознавания голоса |
| `ADMIN_SESSION_SECRET` | Случайная строка ≥32 символов |
| `CATALOG_PUBLIC_BASE_URL` | Публичный URL админки (для фото в Telegram) |
| `ADMIN_DASHBOARD_URL` | То же |

**Не передавать** исполнителем в открытом виде: рабочий `.env` с прод-ключами. Заказчик заполняет свои.

---

## 5. Чеклист приёмки

- [ ] Бот отвечает на `/start` и «Подобрать кухню»
- [ ] Карусель каталога с фото и ценами
- [ ] Вопрос «сколько доставка» — город из **Настройки → Город**
- [ ] Запрос «менеджер» → запрос телефона → уведомление в группу
- [ ] Заявка видна в дашборде **Заявки** (поиск пустой)
- [ ] Загрузка фото в **Каталог** работает
- [ ] `/admin` в Telegram (id в `TELEGRAM_ADMIN_IDS`)
- [ ] Голосовые распознаются (ключ ProxyAPI)
- [ ] **Настройки → Брошенная воронка** — таймаут эскалации (мин. 10 мин)
- [ ] **Журнал эскалаций** — записи при брошенной воронке и передаче менеджеру
- [ ] Пароль `1111` сменён

---

## 6. Повторный экспорт БД (если данные обновились)

На сервере с работающим `kitchens-postgres`:

```bash
cd /opt/kitchens-bot
bash scripts/export_handover_db.sh
# скопировать delivery/kitchens_bot_handover.dump заказчику
```

---

## 7. Сборка ZIP для передачи

```powershell
.\scripts\build_handover_package.ps1
```

Создаёт `delivery/KitchensProduction-handover.zip` (код + дамп + инструкции, без `.env`, `.venv`, секретов).

---

## 8. Поддержка и файлы

- Пользовательская инструкция: `READMEUser.md`
- Логи бота: `journalctl -u kitchens-bot.service -f`
- Логи админки: `journalctl -u kitchens-admin.service -f`
- Сброс пароля админки: `python scripts/reset_admin_password.py` (нужен `DATABASE_URL` в `.env`)
