# Implementation Plan: Автоматический деплой на демо-сервер

**Branch**: `002-deploy` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

## Summary

GitHub Actions при пуше в `main` доставляет репозиторий на сервер через rsync, пересобирает контейнер `docker compose up -d --build` и проверяет `/api/v1/health`. Сервер готовится один раз скриптом; секреты живут в GitHub Secrets и в `.env` на сервере.

## Technical Context

**Runner**: `ubuntu-latest`, стандартные `rsync`, `ssh`, `docker compose` — без сторонних actions, кроме `actions/checkout`.

**Сервер**: Ubuntu, Docker CE + compose-plugin, каталог `/opt/ai-gpr-center`, порт 8000 наружу.

**Доставка**: rsync с раннера. Альтернатива `git pull` на сервере отвергнута: потребовала бы deploy-key к приватному репозиторию на сервере — лишняя точка утечки.

**Секреты**: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (ключ `~/.ssh/ai-gpr-deploy`, только для деплоя) — заданы 03.09.2026. `APP_ENV` — содержимое `backend/.env`. Пуш в репозиторий с машины PM — через deploy key `~/.ssh/ai-gpr-github` с правом записи: OAuth-токен `gh` не может создавать workflow-файлы без scope `workflow`, SSH-ключ этого ограничения не имеет.

**Выключатель**: `vars.DEPLOY_ENABLED` — job не создаётся, пока не `true`.

**Performance Goals**: пуш → health OK ≤ 10 мин (SC-201).

**Constraints**: без TLS, без домена, без отката — зафиксировано в Assumptions спецификации.

## Constitution Check

| Принцип | Проверка |
|---|---|
| VI. Демо важнее архитектуры | один compose, один хост, без оркестрации — ✅ |
| Границы скоупа: ИБ вне скоупа | деплой от root принят осознанно, отдельный пользователь — путь развития; секреты при этом вне репозитория — ✅ |
| Рабочий процесс: код по задаче | правка S3-полей — T094 из фазы 1.5, перенос compose — T101 — ✅ |

## Project Structure

```text
.github/workflows/deploy.yml   # пайплайн
docker-compose.yml             # корень репозитория (перенесён из news_parser/, T101)
deploy/bootstrap.sh            # первичная настройка сервера, без секретов
specs/002-deploy/
├── spec.md
├── plan.md
├── quickstart.md              # что делает человек: ключ, секреты, .env
└── tasks.md
```

## Цель деплоя

Только `backend/` (FR-210). Job `check` смотрит на `backend/Dockerfile`; без него job `deploy` пропускается — в интерфейсе Actions это видно как skipped, а не как успех. `news_parser/` исключён из rsync и имеет собственный dev-compose внутри каталога.

## Ход деплоя

1. `check`: есть ли `backend/Dockerfile` → `ready`.
2. `docker compose config` на раннере — ловит синтаксис до сервера.
3. SSH-ключ из секрета → `~/.ssh/deploy_key`, `ssh-keyscan` хоста.
4. `deploy/bootstrap.sh` по SSH — Docker, каталог, порт; идемпотентно (FR-211).
5. `rsync --delete` с исключениями: `.git`, `.github`, `.env`, `backend/.env`, `backend/data`, `news_parser/`, `context/`, `specs/`, `docs/`.
6. `backend/.env` из секрета `APP_ENV`, иначе пустой файл и предупреждение (FR-212).
7. `docker compose up -d --build --remove-orphans`.
8. Health gate: до 24 попыток по 5 с на `/api/health`; провал → `compose ps` + логи + exit 1.

## Что сделано в коде ради запускаемости

`news_parser/app/config.py`: S3-поля были обязательными без значения по умолчанию, приложение не стартовало без Cloud.ru. Сделаны опциональными, добавлено свойство `s3_enabled`; `parser_service.py` выгружает в S3 только при `s3_enabled`. Это часть T094; полное удаление S3 — по-прежнему в фазе 1.5.

## Complexity Tracking

Не заполняется: нарушений конституции нет.
