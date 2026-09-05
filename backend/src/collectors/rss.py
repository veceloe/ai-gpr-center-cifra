"""RSS-ленты СМИ — FR-002."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from time import struct_time

import httpx

from src.collectors.base import CollectedItem, register_adapter
from src.models import Source, SourceType
from src.pipeline.normalize import clean_text, extract_from_html

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30.0
USER_AGENT = "ai-gpr-center/0.1 (industry monitoring prototype)"
MAX_CONCURRENT_ARTICLES = 4


def _to_datetime(parsed: struct_time | None) -> datetime | None:
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=UTC)
    except (TypeError, ValueError):  # pragma: no cover - битая дата в ленте
        return None


class RssAdapter:
    source_type = SourceType.RSS

    async def fetch(self, source: Source, limit: int) -> list[CollectedItem]:
        import feedparser

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            response = await client.get(source.url)
            response.raise_for_status()
            body = response.content

        # feedparser синхронный и на больших лентах заметно считает — в отдельный поток.
        feed = await asyncio.to_thread(feedparser.parse, body)
        if feed.bozo and not feed.entries:
            raise ValueError(f"лента не разобрана: {getattr(feed, 'bozo_exception', 'неизвестно')}")

        items: list[CollectedItem] = []
        for entry in feed.entries[:limit]:
            link = (entry.get("link") or "").strip()
            if not link:
                continue

            body_html = ""
            if entry.get("content"):
                body_html = entry["content"][0].get("value", "")
            body_html = body_html or entry.get("summary", "") or entry.get("description", "")
            text = extract_from_html(body_html) if "<" in body_html else clean_text(body_html)

            items.append(
                CollectedItem(
                    url=link,
                    title=clean_text(entry.get("title", "")),
                    raw_text=text,
                    published_at=_to_datetime(
                        entry.get("published_parsed") or entry.get("updated_parsed")
                    ),
                    external_id=entry.get("id") or link,
                )
            )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_ARTICLES)
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:

            async def enrich(item: CollectedItem) -> None:
                async with semaphore:
                    try:
                        response = await client.get(item.url)
                        response.raise_for_status()
                    except httpx.HTTPError as exc:
                        logger.debug("RSS-материал %s недоступен: %s", item.url, str(exc)[:120])
                        return
                full_text = extract_from_html(response.text)
                # Некоторые RSS уже содержат полный текст; не заменяем его короткой
                # страницей-заглушкой или paywall-анонсом.
                if len(full_text) > len(item.raw_text):
                    item.raw_text = full_text

            await asyncio.gather(*(enrich(item) for item in items))
        return items


register_adapter(RssAdapter())
