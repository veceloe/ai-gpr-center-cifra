# news_parser — драфт, ядро дорожки E1

Перенесён из другого проекта; интегрируется в `backend/` по фазе 1.5 `specs/001-ai-monitoring-center/tasks.md` (T092–T102). До переноса — это единственный запускаемый код в репозитории.

## Локальный запуск (проверено 03.09.2026)

Нужен Python ≥ 3.10 — в коде синтаксис `X | None`. Системный 3.9 не подойдёт.

```bash
cd news_parser
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
```

Обязательные переменные окружения (все без значений по умолчанию): `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`. S3 — опционален с 03.09, без него выгрузка просто не выполняется.

Старт без реальных ключей, только чтобы поднять API:

```bash
TELEGRAM_API_ID=1 TELEGRAM_API_HASH=dummy TELEGRAM_PHONE=+70000000000 \
LLM_API_KEY=dummy LLM_BASE_URL=http://127.0.0.1:9/v1 LLM_MODEL=dummy \
API_PORT=8010 .venv/bin/python -m app.main
```

## Что происходит при старте без сессии Telegram

Сервер поднимается, создаёт `data/news.db` с таблицами `posts`, `topics`, `topic_posts`, запускает планировщик. Прогрев в фоне подключается к Telegram, получает `RuntimeError: Telegram session is not authorized` — ошибка **перехватывается**, процесс живёт. Это ожидаемое поведение, не баг.

Результат smoke-теста 03.09.2026 на пустой базе:

| Запрос | Ответ |
|---|---|
| `GET /api/v1/health` | 200 `{"status":"ok"}` |
| `GET /api/v1/topics?period=day` | 200, `topics: []` |
| `GET /api/v1/topics?period=bogus` | 422, понятное сообщение валидации |
| `GET /api/v1/topics/999/news` | 404 `Topic not found` |
| `GET /openapi.json` | 200 |

Реальная сессия: `python -m scripts.auth_telegram` → строка в `TELEGRAM_STRING_SESSION`.

## Что здесь не так относительно спецификации

Полный список — фаза 1.5 в `tasks.md`. Два архитектурных пункта, которые надо решить до любого развития кода:

- **T099** — `_clear_topics` удаляет все топики при каждом пересчёте: правки пользователя пропадут, ID меняются. Принцип IV конституции.
- **T100** — кластеризация отправляет весь период одним вызовом модели; на месяце данных это больше миллиона символов.

Промпт `FILTER_SYSTEM_PROMPT` (маркетинг Сбера) и `s3_writer.py` — чужой домен, вырезаются (T093, T094).
