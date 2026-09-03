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

## Phase 4: Ручные шаги

- [x] T209 Ключ деплоя `~/.ssh/ai-gpr-deploy` сгенерирован; секреты `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` и переменная `DEPLOY_ENABLED=true` заданы
- [ ] T210 [PM] **Единственный шаг с паролем**: положить публичный ключ на сервер — `ssh-copy-id -i ~/.ssh/ai-gpr-deploy.pub root@<HOST>`
- [ ] T211 [E1/PM] Задать `APP_ENV` содержимым `backend/.env`, когда появятся ключи LLM: `gh secret set APP_ENV < backend/.env`
- [ ] T212 [PM] Сменить пароль root — он передавался текстом; после T210 он не нужен
- [ ] T213 Автоматически: первый пуш с `backend/Dockerfile` задеплоит backend; проверка — `curl http://<HOST>:8000/api/health`

- [x] T214 `deploy/deploy.sh` — запасной деплой с рабочей машины теми же шагами, пока Actions не запускается
- [ ] T215 [PM] Открыть https://github.com/veceloe/ai-gpr-center-cifra/actions — прочитать причину `startup_failure` в баннере запуска; проверить https://github.com/settings/billing (Actions для приватных репо)
- [ ] T216 [PM] Сервер: порт 22 отвечает `Connection refused` — SSH не запущен или на другом порту; проверить в панели хостинга

## Phase 5: Готовность backend

Деплой начинается не по этой фиче, а по фиче 001: как только `backend/Dockerfile` появится в `main`, job `check` даст `ready=true`. Задачи T001–T002, T092 фичи 001 создают `backend/`; `Dockerfile` — часть T001.

## Notes

Пароль сервера агентом не используется и не хранится — T210 делает человек. Остальное выполнено агентом 03.09.2026.
