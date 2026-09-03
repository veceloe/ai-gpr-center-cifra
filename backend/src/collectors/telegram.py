"""Telegram-каналы через Telethon — ADR-0008.

Основа перенесена из драфта `news_parser` Ивана Артемьева: StringSession для работы
без файла сессии, разбор прокси с исправленной передачей учётных данных. Драфт
подтвердил, что авторизация решаема, и это перевернуло ADR-0004, выбиравший
веб-версию t.me/s/ ради избежания возни с ключами.

Отличие от драфта: сбор инкрементальный по `min_id`. Драфт перечитывал 200 последних
сообщений каждый цикл — лишняя нагрузка и риск floodwait (задача T097).
"""

from __future__ import annotations

import logging
from datetime import UTC
from urllib.parse import urlparse

from src.collectors.base import CollectedItem, register_adapter
from src.config import get_settings
from src.models import Source, SourceType
from src.pipeline.normalize import clean_text

logger = logging.getLogger(__name__)

_SUPPORTED_PROXY_SCHEMES = frozenset({"http", "socks4", "socks5"})


def normalize_channel(raw: str) -> str:
    """Приводит ссылку или @имя к чистому username канала."""
    value = raw.strip()
    for prefix in ("https://t.me/s/", "https://t.me/", "http://t.me/", "t.me/"):
        if value.startswith(prefix):
            value = value[len(prefix) :].split("/")[0]
            break
    return value.lstrip("@")


def parse_proxy(raw: str) -> dict | None:
    """Прокси из строки `socks5://user:pass@host:port`.

    Telethon ожидает словарь с `rdns`. В драфте передавался пятиэлементный кортеж
    без него, из-за чего логин и пароль съезжали и прокси возвращал 407.
    """
    value = raw.strip()
    if not value:
        return None
    if "://" not in value:
        value = f"http://{value}"

    parsed = urlparse(value)
    scheme = "http" if parsed.scheme.lower() == "https" else parsed.scheme.lower()
    if scheme not in _SUPPORTED_PROXY_SCHEMES:
        raise ValueError(f"неподдерживаемая схема прокси {scheme!r}: нужен http, socks4 или socks5")
    if not parsed.hostname:
        raise ValueError(f"в TELEGRAM_PROXY нет хоста: {raw!r}")

    proxy: dict = {
        "proxy_type": scheme,
        "addr": parsed.hostname,
        "port": parsed.port or (8080 if scheme == "http" else 1080),
        "rdns": True,
    }
    if parsed.username:
        proxy["username"] = parsed.username
        proxy["password"] = parsed.password or ""
    return proxy


class TelegramAdapter:
    source_type = SourceType.TELEGRAM

    async def fetch(self, source: Source, limit: int) -> list[CollectedItem]:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.types import Message

        settings = get_settings()
        if not settings.telegram_configured:
            raise RuntimeError(
                "Telegram не настроен: нужны TELEGRAM_API_ID, TELEGRAM_API_HASH и "
                "TELEGRAM_STRING_SESSION. Сессия создаётся один раз: python -m src.cli telegram-login"
            )

        proxy = parse_proxy(settings.telegram_proxy)
        client = TelegramClient(
            StringSession(settings.telegram_string_session),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            **({"proxy": proxy} if proxy else {}),
        )

        username = normalize_channel(source.url)
        # Инкрементальный сбор: только сообщения новее последнего сохранённого.
        min_id = int(source.last_external_id) if (source.last_external_id or "").isdigit() else 0

        await client.connect()
        try:
            if not await client.is_user_authorized():
                # Запрос кода намеренно не отправляется: на сервере это спамит SMS
                # и ведёт к floodwait. Авторизация делается офлайн один раз.
                raise RuntimeError(
                    "Сессия Telegram не авторизована. Создайте её: python -m src.cli telegram-login"
                )

            entity = await client.get_entity(username)
            items: list[CollectedItem] = []
            async for message in client.iter_messages(entity, limit=limit, min_id=min_id):
                if not isinstance(message, Message) or not message.message:
                    continue
                published = message.date
                if published and published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)

                text = clean_text(message.message)
                items.append(
                    CollectedItem(
                        url=f"https://t.me/{username}/{message.id}",
                        title=_derive_title(text),
                        raw_text=text,
                        published_at=published,
                        external_id=str(message.id),
                    )
                )
            logger.info("Telegram @%s: получено %s сообщений (min_id=%s)", username, len(items), min_id)
            return items
        finally:
            await client.disconnect()


def _derive_title(text: str) -> str:
    """У поста в Telegram нет заголовка — берём первую строку или первое предложение."""
    first_line = text.split("\n", 1)[0].strip()
    if 0 < len(first_line) <= 200:
        return first_line
    sentence = text.split(". ", 1)[0].strip()
    return (sentence[:197] + "...") if len(sentence) > 200 else sentence or "Без заголовка"


register_adapter(TelegramAdapter())
