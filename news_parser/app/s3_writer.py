import asyncio
import logging
from datetime import datetime
from io import BytesIO
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.config import Config

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_s3_client() -> boto3.client:
    settings = get_settings()
    endpoint = settings.s3_endpoint_url
    access_key = settings.s3_access_key
    secret_key = settings.s3_secret_key

    if not access_key or not secret_key:
        logger.warning("S3_ACCESS_KEY and/or S3_SECRET_KEY not set — S3 writes will fail")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            s3={"addressing_style": "virtual"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            signature_version="s3v4",
        ),
    )


def _posts_to_arrow(posts: list[dict[str, Any]]) -> pa.Table:
    """Конвертирует список dict (постов) в PyArrow Table.

    Поле `id` не включается — оно генерируется SQLite при INSERT.
    Основной уникальный ключ — (channel_username, message_id).
    """
    if not posts:
        return pa.table({
            "channel_username": pa.array([], type=pa.string()),
            "channel_title": pa.array([], type=pa.string()),
            "message_id": pa.array([], type=pa.int64()),
            "text": pa.array([], type=pa.string()),
            "url": pa.array([], type=pa.string()),
            "published_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            "fetched_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
        })

    channel_usernames = [p["channel_username"] for p in posts]
    channel_titles = [p["channel_title"] if p["channel_title"] is not None else None for p in posts]
    message_ids = [p["message_id"] for p in posts]
    texts = [p["text"] for p in posts]
    urls = [p["url"] if p["url"] is not None else None for p in posts]
    published_ats = [
        p["published_at"] if isinstance(p["published_at"], datetime) else datetime.fromisoformat(p["published_at"])
        for p in posts
    ]
    fetched_ats = [
        p["fetched_at"] if isinstance(p["fetched_at"], datetime) else datetime.fromisoformat(p["fetched_at"])
        for p in posts
    ]

    return pa.table({
        "channel_username": pa.array(channel_usernames, type=pa.string()),
        "channel_title": pa.array(channel_titles, type=pa.string()),
        "message_id": pa.array(message_ids, type=pa.int64()),
        "text": pa.array(texts, type=pa.string()),
        "url": pa.array(urls, type=pa.string()),
        "published_at": pa.array(published_ats, type=pa.timestamp("us", tz="UTC")),
        "fetched_at": pa.array(fetched_ats, type=pa.timestamp("us", tz="UTC")),
    })


def _upload_batch_sync(posts_batch: list[dict[str, Any]]) -> int:
    """Batch-запись постов в единый parquet-файл в S3.

    Логика (как в SQLite):
    1. Прочитать существующий parquet один раз
    2. Отфильтровать дубли по (channel_username, message_id)
    3. Конкатенировать и записать один раз

    Возвращает: количество добавленных записей.
    """
    s3 = _get_s3_client()
    settings = get_settings()

    try:
        # 1. Читаем существующий parquet
        existing = None
        existing_ids: set[tuple[str, int]] = set()
        try:
            response = s3.get_object(Bucket=settings.s3_bucket, Key=f"{settings.s3_prefix}/posts.parquet")
            existing_bytes = response["Body"].read()
            existing = pq.read_table(BytesIO(existing_bytes))
            existing_ids = {
                (row["channel_username"], row["message_id"])
                for row in existing.to_pylist()
            }
            logger.info(
                "Read existing parquet at s3://%s/%s (%d records)",
                settings.s3_bucket,
                f"{settings.s3_prefix}/posts.parquet",
                len(existing_ids),
            )
        except s3.exceptions.ClientError:
            logger.info(
                "No existing parquet at s3://%s/%s — creating new",
                settings.s3_bucket,
                f"{settings.s3_prefix}/posts.parquet",
            )

        # 2. Фильтруем дубликаты
        unique_new = [
            post for post in posts_batch
            if (post["channel_username"], post["message_id"]) not in existing_ids
        ]
        skipped = len(posts_batch) - len(unique_new)
        if skipped:
            logger.debug("Skipped %d duplicate posts", skipped)

        if not unique_new:
            return 0

        # 3. Конкатенируем и записываем один раз
        new_table = _posts_to_arrow(unique_new)
        if existing is not None:
            merged = pa.concat_tables([existing, new_table])
        else:
            merged = new_table

        buffer = BytesIO()
        pq.write_table(merged, buffer)
        buffer.seek(0)

        s3.put_object(Bucket=settings.s3_bucket, Key=f"{settings.s3_prefix}/posts.parquet", Body=buffer.read())
        logger.info(
            "Uploaded %d new posts to s3://%s/%s (total: %d)",
            len(unique_new),
            settings.s3_bucket,
            f"{settings.s3_prefix}/posts.parquet",
            len(existing_ids) + len(unique_new),
        )
        return len(unique_new)

    except Exception:
        logger.exception(
            "Failed to upload batch of %d posts to S3 (%s/%s). "
            "This is non-critical — data is still available via SQLite.",
            len(posts_batch),
            settings.s3_bucket,
            f"{settings.s3_prefix}/posts.parquet",
        )
        return 0


async def upload_posts_to_s3(posts: list[dict[str, Any]]) -> int:
    """Загружает батч постов в S3 одной операцией (без race condition).

    Возвращает количество добавленных записей.
    """
    if not posts:
        return 0

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _upload_batch_sync, posts)
