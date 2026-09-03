# Quickstart: ввод сервера в строй

Три шага делает человек — все связаны с секретами, которые не должны проходить через агента, чат или репозиторий.

## Шаг 1. Ключ деплоя

Отдельный ключ только для CI — не личный:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/ai-gpr-deploy -N "" -C "github-actions-deploy"
```

Публичную часть — на сервер (спросит пароль root один раз):

```bash
ssh-copy-id -i ~/.ssh/ai-gpr-deploy.pub root@<HOST>
```

## Шаг 2. Сервер

```bash
ssh -i ~/.ssh/ai-gpr-deploy root@<HOST> 'bash -s' < deploy/bootstrap.sh
```

Затем на сервере создать `/opt/ai-gpr-center/news_parser/.env` из `news_parser/.env.example`. Обязательные: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, `TELEGRAM_STRING_SESSION` (из `python -m scripts.auth_telegram` локально), `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`. S3 — не заполнять.

## Шаг 3. Секреты GitHub и выключатель

```bash
gh secret set DEPLOY_HOST --body "<HOST>"
gh secret set DEPLOY_USER --body "root"
gh secret set DEPLOY_SSH_KEY < ~/.ssh/ai-gpr-deploy
gh variable set DEPLOY_ENABLED --body "true"
```

## Проверка

```bash
gh workflow run deploy.yml && sleep 20 && gh run watch
curl http://<HOST>:8000/api/v1/health
```

Ожидаемо: `{"status":"ok"}`. Дальше каждый пуш в `main` деплоит сам.

## После настройки

Сменить пароль root, если он передавался текстом где бы то ни было. Ключ деплоя его заменяет полностью; парольный вход по SSH можно отключить.
