#!/usr/bin/env bash
# Запасной путь деплоя — те же шаги, что в .github/workflows/deploy.yml, но с рабочей машины.
# Нужен, пока GitHub Actions в приватном репозитории не запускается (startup_failure на любом workflow).
#
#   deploy/deploy.sh                      # деплой backend/ на сервер из secrets/окружения
#   DEPLOY_HOST=1.2.3.4 deploy/deploy.sh  # переопределить хост
#
# Ключ: ~/.ssh/ai-gpr-deploy (публичная часть должна лежать на сервере).
# Конфиг приложения: backend/.env локально → копируется на сервер.
set -euo pipefail

HOST="${DEPLOY_HOST:-185.56.162.154}"
USER_="${DEPLOY_USER:-root}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/ai-gpr-deploy}"
APP_DIR=/opt/ai-gpr-center
SSH="ssh -i $KEY -o IdentitiesOnly=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

step "0/6 Готов ли backend"
[ -f backend/Dockerfile ] || { echo "backend/Dockerfile нет — деплоится только готовый backend. Стоп."; exit 2; }
docker compose -f docker-compose.yml config --quiet 2>/dev/null || echo "(docker локально нет — compose проверится на сервере)"

step "1/6 Доступ к серверу $USER_@$HOST"
$SSH "$USER_@$HOST" 'echo "  ssh ok: $(hostname)"' || { echo "нет доступа по ключу $KEY — сначала: ssh-copy-id -i $KEY.pub $USER_@$HOST"; exit 1; }

step "2/6 Подготовка сервера (идемпотентно)"
$SSH "$USER_@$HOST" 'bash -s' < deploy/bootstrap.sh

step "3/6 Доставка кода"
rsync -az --delete \
  --exclude '.git' --exclude '.github' \
  --exclude '.env' --exclude 'backend/.env' --exclude 'backend/data' \
  --exclude 'news_parser' --exclude 'context' --exclude 'specs' --exclude 'docs' \
  -e "$SSH" ./ "$USER_@$HOST:$APP_DIR/"

step "4/6 Конфигурация"
if [ -f backend/.env ]; then
  $SSH "$USER_@$HOST" "umask 077; cat > $APP_DIR/backend/.env" < backend/.env; echo "  backend/.env скопирован"
else
  $SSH "$USER_@$HOST" "touch $APP_DIR/backend/.env"; echo "  ВНИМАНИЕ: локального backend/.env нет — на сервере пустой, LLM работать не будет"
fi

step "5/6 Сборка и запуск"
$SSH "$USER_@$HOST" "cd $APP_DIR && docker compose up -d --build --remove-orphans"

step "6/7 Health gate"
# Порт снаружи контейнера — 8239 (compose пробрасывает 8239:8000). Раньше здесь
# стоял 8000, на котором на хосте никто не слушает, и проверка не могла пройти
# в принципе: рабочий деплой объявлялся упавшим.
$SSH "$USER_@$HOST" bash -s <<'REMOTE'
set -uo pipefail
cd /opt/ai-gpr-center
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1:8239/api/health 2>/dev/null)
  if [ "$code" = "200" ]; then echo "  health OK после $((i*5)) с"; exit 0; fi
  sleep 5
done
echo "  backend не ответил за 300 с, последний код: ${code:-нет}"
docker compose ps; docker compose logs --tail 60; exit 1
REMOTE

step "7/7 Данные демо"
# Пустая лента — не демонстрация. Переносим локальную базу с уже обработанными
# материалами. DEPLOY_SEED_DB=0 отключает перенос, если на сервере свои данные.
if [ "${DEPLOY_SEED_DB:-0}" = "1" ] && [ -f backend/data/app.db ]; then
  $SSH "$USER_@$HOST" "cat > /tmp/app.db" < backend/data/app.db
  $SSH "$USER_@$HOST" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/ai-gpr-center
V=/var/lib/docker/volumes/ai-gpr-center_backend_data/_data
docker compose stop backend >/dev/null 2>&1
# Файлы журнала принадлежат прежней базе: при старте они переигрываются поверх
# новой и стирают её содержимое. Удалять обязательно.
rm -f "$V/app.db-wal" "$V/app.db-shm"
cp /tmp/app.db "$V/app.db"
rm -f /tmp/app.db
docker compose start backend >/dev/null
for i in $(seq 1 40); do curl -fsS http://127.0.0.1:8239/api/health >/dev/null 2>&1 && break; sleep 5; done
echo "  база перенесена, материалов в ленте: $(curl -fsS 'http://127.0.0.1:8239/api/feed?limit=1' | python3 -c 'import sys,json; print(json.load(sys.stdin)["total"])')"
REMOTE
else
  echo "  перенос базы пропущен (DEPLOY_SEED_DB=1 включает)"
fi

echo; echo "Задеплоено — http://$HOST/"
