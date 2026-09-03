"""Первичная авторизация Telethon (один раз) → печатает StringSession.

Запусти локально: `python -m scripts.auth_telegram` (нужны TELEGRAM_API_ID/HASH/PHONE
в .env). Введи код из Telegram — скрипт выведет строку, которую надо положить
в CI/CD-переменную TG_SESSION (она едет в секрет как TELEGRAM_STRING_SESSION).
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.telegram_factory import _proxy_kwargs
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    settings = get_settings()
    client = TelegramClient(
        StringSession(),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        **_proxy_kwargs(settings),
    )
    await client.start(phone=settings.telegram_phone)
    me = await client.get_me()
    session_str = client.session.save()
    print(f"\nAuthorized as: {me.first_name} (@{me.username})")
    print("\n=== TELEGRAM_STRING_SESSION (скопируй целиком в CI-переменную TG_SESSION) ===")
    print(session_str)
    print("=== конец ===\n")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
