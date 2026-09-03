import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_channels
from app.models import Post
from app.s3_writer import upload_posts_to_s3
from app.telegram_client import TelegramParser

logger = logging.getLogger(__name__)


async def parse_all_channels(session: AsyncSession) -> int:
    channels = load_channels()
    parser = TelegramParser()
    await parser.connect()
    saved = 0
    s3_rows: list[dict] = []
    try:
        for channel in channels:
            messages = await parser.fetch_channel_messages(channel)
            saved += await _upsert_posts(session, messages)
            # Готовим rows для S3 — те же поля + fetched_at (совпадает с SQLite)
            now = datetime.now(timezone.utc)
            s3_rows.extend({**msg, "fetched_at": now} for msg in messages)
        await session.commit()
        # Один batch-вызов — без race condition
        await upload_posts_to_s3(s3_rows)
    finally:
        await parser.disconnect()
    logger.info("Parser saved %d new posts", saved)
    return saved


async def _upsert_posts(session: AsyncSession, messages: list[dict]) -> int:
    if not messages:
        return 0

    now = datetime.now(timezone.utc)
    rows = [
        {
            **msg,
            "fetched_at": now,
        }
        for msg in messages
    ]

    stmt = sqlite_insert(Post).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["channel_username", "message_id"])
    result = await session.execute(stmt)
    return result.rowcount or 0


async def get_posts_for_period(session: AsyncSession, period_start: datetime, period_end: datetime) -> list[Post]:
    query = (
        select(Post)
        .where(Post.published_at >= period_start)
        .where(Post.published_at < period_end)
        .order_by(Post.published_at.desc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())
