"""Страницы регуляторов — FR-002.

Сайты органов власти не отдают RSS, поэтому список публикаций собирается со страницы.
Ссылки берутся из типовых контейнеров списка новостей, текст — со страницы материала.

Ограничение, названное исследованием прямо: regulation.gov.ru теряет документы —
страницы бывают недоступны днями, а проекты исчезают на месяцы. Поэтому полный текст
сохраняется у нас (`Item.raw_text`), а не подтягивается по ссылке при показе.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx

from src.collectors.base import CollectedItem, register_adapter
from src.models import Source, SourceType
from src.pipeline.normalize import clean_text, extract_from_html

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30.0
USER_AGENT = "ai-gpr-center/0.1 (industry monitoring prototype)"
MAX_CONCURRENT_PAGES = 4

# Контейнеры, в которых органы власти обычно держат список публикаций.
LIST_SELECTORS = (
    "main a",
    "article a",
    ".news-list a",
    ".news a",
    ".list a",
    "[class*=news] a",
    "[class*=item] a",
)


class WebAdapter:
    source_type = SourceType.WEB

    async def fetch(self, source: Source, limit: int) -> list[CollectedItem]:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            index = await client.get(source.url)
            index.raise_for_status()
            links = self._extract_links(index.text, source.url, limit)
            if not links:
                raise ValueError("на странице не найдено ссылок на публикации")

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

            async def load(url: str, title: str) -> CollectedItem | None:
                async with semaphore:
                    try:
                        page = await client.get(url)
                        page.raise_for_status()
                    except httpx.HTTPError as exc:
                        logger.debug("Страница %s недоступна: %s", url, str(exc)[:120])
                        return None
                text = extract_from_html(page.text)
                if not text:
                    return None
                return CollectedItem(url=url, title=title or url, raw_text=text, external_id=url)

            gathered = await asyncio.gather(*(load(u, t) for u, t in links))

        return [item for item in gathered if item is not None]

    def _extract_links(self, html: str, base_url: str, limit: int) -> list[tuple[str, str]]:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        base_host = urlparse(base_url).netloc
        seen: set[str] = set()
        found: list[tuple[str, str]] = []

        for selector in LIST_SELECTORS:
            for node in tree.css(selector):
                href = (node.attributes.get("href") or "").strip()
                if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
                    continue
                absolute = urljoin(base_url, href)
                if urlparse(absolute).netloc != base_host or absolute in seen:
                    continue
                title = clean_text(node.text())
                # Навигационные ссылки коротки; тексты публикаций — нет.
                if len(title) < 20:
                    continue
                seen.add(absolute)
                found.append((absolute, title))
                if len(found) >= limit:
                    return found
            if found:
                break
        return found


register_adapter(WebAdapter())
