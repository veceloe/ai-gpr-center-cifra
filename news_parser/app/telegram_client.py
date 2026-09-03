import logging
from datetime import timezone

from telethon.tl.types import Message

from app.config import ChannelConfig, get_settings, normalize_channel_username
from app.telegram_factory import create_telegram_client

logger = logging.getLogger(__name__)


class TelegramParser:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = create_telegram_client(settings.telegram_session_path, settings)
        self._phone = settings.telegram_phone
        self._limit = settings.fetch_limit_per_channel

    async def connect(self) -> None:
        await self._client.connect()
        if not await self._client.is_user_authorized():
            # НЕ шлём send_code_request: на сервере это спамит SMS-коды и ведёт
            # к floodwait. Авторизация делается офлайн → TG_SESSION (StringSession).
            raise RuntimeError(
                "Telegram session is not authorized. Сгенерь TG_SESSION: python -m scripts.auth_telegram"
            )

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def fetch_channel_messages(self, channel: ChannelConfig) -> list[dict]:
        username = normalize_channel_username(channel.username)
        entity = await self._client.get_entity(username)
        channel_title = channel.title or getattr(entity, "title", None) or username

        results: list[dict] = []
        async for message in self._client.iter_messages(entity, limit=self._limit):
            if not isinstance(message, Message) or not message.message:
                continue
            published = message.date
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)

            results.append(
                {
                    "channel_username": username,
                    "channel_title": channel_title,
                    "message_id": message.id,
                    "text": message.message.strip(),
                    "url": f"https://t.me/{username}/{message.id}",
                    "published_at": published,
                }
            )
        logger.info("Fetched %d messages from @%s", len(results), username)
        return results
