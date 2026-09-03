# Quickstart: ввод сервера в строй

Почти всё сделано. Секреты в GitHub заданы, ключ деплоя сгенерирован, пайплайн ждёт `backend/`.

## Единственный ручной шаг — публичный ключ на сервер

Требует пароля root один раз, поэтому его делает человек:

```bash
ssh-copy-id -i ~/.ssh/ai-gpr-deploy.pub root@<HOST>
```

Проверка, что ключ встал (пароль больше не спросит):

```bash
ssh -i ~/.ssh/ai-gpr-deploy root@<HOST> 'echo ok && docker --version || echo "docker поставит workflow"'
```

## Когда появятся ключи LLM и Telegram

```bash
gh secret set APP_ENV < backend/.env
```

Без этого backend задеплоится, `/api/health` ответит, но обработка материалов работать не будет.

## Что происходит дальше само

Первый пуш в `main`, в котором есть `backend/Dockerfile`, запускает деплой: Docker на сервере, код, `.env`, `compose up`, проверка `/api/health`. Смотреть: `gh run watch`. Проверять: `curl http://<HOST>:8000/api/health`.

## После

Сменить пароль root. Ключ его заменяет; парольный вход по SSH можно отключить.
