#!/usr/bin/env bash
# Первичная настройка демо-сервера. Запускается ОДИН раз, вручную, от root:
#   ssh root@<host> 'bash -s' < deploy/bootstrap.sh
# Ничего секретного внутри нет; ключи и .env добавляются отдельно (см. specs/002-deploy/quickstart.md).
set -euo pipefail

APP_DIR=/opt/ai-gpr-center

echo "== 1/4 Docker и rsync =="
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg rsync
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
  apt-get install -y -qq rsync >/dev/null 2>&1 || true
fi
systemctl enable --now docker
docker compose version

echo "== 2/4 Каталог приложения =="
mkdir -p "$APP_DIR/news_parser"

echo "== 3/4 Файрвол (если ufw активен) =="
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow 22/tcp >/dev/null
  ufw allow 8000/tcp >/dev/null
  echo "открыт порт 8000"
fi

echo "== 4/4 Что осталось сделать руками =="
cat <<'TXT'
  1. Положить публичный ключ деплоя в ~/.ssh/authorized_keys этого пользователя.
  2. Создать /opt/ai-gpr-center/news_parser/.env из news_parser/.env.example:
     нужны TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, TELEGRAM_STRING_SESSION,
     LLM_API_KEY, LLM_BASE_URL, LLM_MODEL. S3 можно не заполнять.
  3. Сменить пароль root, если он когда-либо передавался текстом.
Готово: дальше деплоит GitHub Actions при пуше в main.
TXT
