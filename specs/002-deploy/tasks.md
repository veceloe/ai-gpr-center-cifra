---
description: "Task list for 002-deploy"
---

# Tasks: Автоматический деплой на демо-сервер

**Input**: `specs/002-deploy/`

## Phase 1: Запускаемость приложения

- [x] T201 [E1] S3-поля в `news_parser/app/config.py` опциональны, `s3_enabled`; `parser_service.py` выгружает только при включённом S3 (FR-209; часть T094 фазы 1.5 фичи 001)
- [x] T202 [E1] `docker-compose.yml` в корне репозитория, `ports: 8000:8000`, имена без следов чужого проекта (T101 фичи 001)

## Phase 2: Пайплайн

- [x] T203 `.github/workflows/deploy.yml`: push в main + workflow_dispatch, gate `vars.DEPLOY_ENABLED`, concurrency (FR-201, FR-202, FR-206)
- [x] T204 Доставка rsync с исключениями `.env`, данных, `context/` (FR-203, FR-204)
- [x] T205 Health gate 120 с с логами при провале (FR-205)
- [x] T206 Проверка наличия секретов и `.env` до сетевых действий (FR-207)

## Phase 3: Сервер

- [x] T207 `deploy/bootstrap.sh`: Docker, compose-plugin, rsync, каталог, ufw (FR-208)
- [x] T208 `quickstart.md`: ключ, секреты, `.env`, проверка (SC-204)

## Phase 4: Ручные шаги — только владелец репозитория

- [ ] T209 [PM] Сгенерировать ключ деплоя, положить публичную часть на сервер
- [ ] T210 [PM] Выполнить `bootstrap.sh`, создать `.env` на сервере
- [ ] T211 [PM] Задать `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, включить `DEPLOY_ENABLED`
- [ ] T212 [PM] Запустить workflow вручную, убедиться в `{"status":"ok"}` (SC-201, SC-202)
- [ ] T213 [PM] Сменить пароль root

## Notes

T209–T213 не выполняются агентом по правилу: пароли, ключи и токены не вводятся и не хранятся. `quickstart.md` даёт команды готовыми.
