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
import re
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

import httpx

from src.collectors.base import CollectedItem, register_adapter
from src.models import Source, SourceType
from src.pipeline.normalize import clean_text, extract_from_html

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30.0
USER_AGENT = "ai-gpr-center/0.1 (industry monitoring prototype)"
MAX_CONCURRENT_PAGES = 4
MAX_DOCUMENTS_PER_ITEM = 5
DOCUMENT_EXTENSIONS = frozenset({".pdf", ".docx", ".doc", ".txt", ".rtf"})
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

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
            host = urlparse(source.url).netloc.lower().removeprefix("www.")
            if host == "regulation.gov.ru":
                return await self._fetch_regulation(client, limit)

            if host == "sozd.duma.gov.ru":
                links = await self._fetch_sozd_links(client, limit)
            else:
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
                document_links = self._extract_document_links(page.text, url)
                snapshots = await asyncio.gather(
                    *(self._load_document(client, semaphore, link) for link in document_links)
                )
                full_documents = [snapshot for snapshot in snapshots if snapshot]
                if full_documents:
                    text = clean_text(
                        f"{text}\n\nПолный текст документа:\n\n"
                        + "\n\n".join(full_documents)
                    )
                if not text:
                    return None
                return CollectedItem(url=url, title=title or url, raw_text=text, external_id=url)

            gathered = await asyncio.gather(*(load(u, t) for u, t in links))

        return [item for item in gathered if item is not None]

    async def _fetch_sozd_links(
        self,
        client: httpx.AsyncClient,
        limit: int,
    ) -> list[tuple[str, str]]:
        """СОЗД рендерит список через JS; официальный Duma API отдаёт его как RSS."""
        import feedparser

        response = await client.get(
            "http://api.duma.gov.ru/api/search.rss",
            params={"law_type": 38, "status": 2},
        )
        response.raise_for_status()
        feed = await asyncio.to_thread(feedparser.parse, response.content)
        if feed.bozo and not feed.entries:
            raise ValueError("RSS Государственной Думы не разобран")
        return [
            (
                str(entry.get("link") or "").strip(),
                clean_text(str(entry.get("title") or "")),
            )
            for entry in feed.entries[:limit]
            if entry.get("link")
        ]

    async def _fetch_regulation(
        self,
        client: httpx.AsyncClient,
        limit: int,
    ) -> list[CollectedItem]:
        """Новый regulation.gov.ru — SPA; проекты и файлы доступны через public API."""
        response = await client.post(
            "https://regulation.gov.ru/api/public/PublicProjects/GetFiltered",
            json={
                "listParams": {
                    "filterModel": {
                        "filters": "",
                        "page": 1,
                        "pageSize": limit,
                    }
                },
                "orderedFields": [
                    "id",
                    "title",
                    "startPublicDiscussion",
                    "stage",
                    "status",
                ],
            },
        )
        response.raise_for_status()
        projects = response.json().get("result", [])
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

        async def load(project: dict) -> CollectedItem | None:
            project_id = str(project.get("id") or "").strip()
            if not project_id:
                return None
            async with semaphore:
                card_response, stages_response = await asyncio.gather(
                    client.get(
                        "https://regulation.gov.ru/api/public/"
                        f"PublicProjects/GetCardInfo/{project_id}"
                    ),
                    client.get(
                        "https://regulation.gov.ru/api/public/"
                        f"PublicProjects/GetProjectStages/{project_id}"
                    ),
                )
            card_response.raise_for_status()
            stages_response.raise_for_status()
            card = card_response.json()
            stages = stages_response.json()

            files: list[tuple[str, str]] = []
            for stage in stages:
                for key in ("file", "modifiedFile"):
                    file_info = stage.get(key)
                    if not isinstance(file_info, dict) or not file_info.get("fileId"):
                        continue
                    files.append(
                        (
                            str(file_info["fileId"]),
                            str(file_info.get("description") or ""),
                        )
                    )
            snapshots = await asyncio.gather(
                *(
                    self._load_document(
                        client,
                        semaphore,
                        "https://regulation.gov.ru/api/public/Files/GetFile/" + file_id,
                        filename=filename,
                    )
                    for file_id, filename in files[:MAX_DOCUMENTS_PER_ITEM]
                )
            )
            document_texts = [text for text in snapshots if text]

            metadata = [
                str(card.get("title") or project.get("title") or ""),
                f"Идентификатор проекта: {card.get('projectId') or project_id}",
                f"Стадия: {project.get('stage') or ''}",
                f"Статус: {project.get('status') or ''}",
            ]
            department = card.get("developerDepartment")
            if isinstance(department, dict) and department.get("description"):
                metadata.append(f"Разработчик: {department['description']}")
            procedure = card.get("procedure")
            if isinstance(procedure, dict) and procedure.get("description"):
                metadata.append(f"Процедура: {procedure['description']}")
            for stage in stages:
                if stage.get("description"):
                    metadata.append(str(stage["description"]))
            if document_texts:
                metadata.extend(["Полный текст документа:", *document_texts])

            published_at = None
            if project.get("startPublicDiscussion"):
                published_at = datetime.fromisoformat(project["startPublicDiscussion"])
            return CollectedItem(
                url=f"https://regulation.gov.ru/projects/{project_id}/",
                title=clean_text(str(card.get("title") or project.get("title") or project_id)),
                raw_text=clean_text("\n\n".join(metadata)),
                published_at=published_at,
                external_id=project_id,
            )

        gathered = await asyncio.gather(*(load(project) for project in projects))
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

    def _extract_document_links(self, html: str, base_url: str) -> list[str]:
        """Ссылки на файлы проекта НПА, которые портал позднее может удалить."""
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        seen: set[str] = set()
        links: list[str] = []
        for node in tree.css("a[href]"):
            href = (node.attributes.get("href") or "").strip()
            absolute = urljoin(base_url, href)
            path = unquote(urlparse(absolute).path).lower()
            extension = PurePosixPath(path).suffix
            is_download = any(token in path for token in ("/download", "/file/", "/attachment/"))
            if extension not in DOCUMENT_EXTENSIONS and not is_download:
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            links.append(absolute)
            if len(links) >= MAX_DOCUMENTS_PER_ITEM:
                break
        return links

    async def _load_document(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        url: str,
        filename: str | None = None,
    ) -> str:
        try:
            async with semaphore:
                response = await client.get(url)
                response.raise_for_status()
            header_name = _filename_from_disposition(
                response.headers.get("content-disposition", "")
            )
            return await asyncio.to_thread(
                self._extract_document_text,
                response.content,
                header_name or filename or url,
                response.headers.get("content-type", ""),
                response.encoding,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Не удалось сохранить полный текст документа %s: %s", url, str(exc)[:160])
            return ""

    @staticmethod
    def _extract_document_text(
        content: bytes,
        url: str,
        content_type: str,
        encoding: str | None,
    ) -> str:
        path = unquote(urlparse(url).path).lower()
        extension = PurePosixPath(path).suffix
        media_type = content_type.split(";", 1)[0].strip().lower()
        # regulation.gov.ru отдаёт вложения как application/octet-stream
        # без расширения в URL — определяем формат по сигнатуре файла.
        if extension not in DOCUMENT_EXTENSIONS:
            if content.startswith(b"%PDF"):
                extension = ".pdf"
            elif content[:2] == b"PK":
                extension = ".docx"
            elif content.startswith(OLE_MAGIC):
                extension = ".doc"
            elif content.lstrip().startswith(b"{\\rtf"):
                extension = ".rtf"

        if extension == ".pdf" or media_type == "application/pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            return clean_text("\n\n".join(page.extract_text() or "" for page in reader.pages))

        if extension == ".docx" or "wordprocessingml" in media_type:
            from docx import Document

            document = Document(BytesIO(content))
            return clean_text("\n".join(paragraph.text for paragraph in document.paragraphs))

        if (
            extension == ".doc"
            or media_type == "application/msword"
            or content.startswith(OLE_MAGIC)
        ):
            return _extract_ole_text(content)

        if extension == ".rtf" or media_type in {"application/rtf", "text/rtf"}:
            decoded = content.decode(encoding or "utf-8", errors="replace")
            return clean_text(re.sub(r"\\[a-z]+\d* ?|[{}]", "", decoded))

        if extension == ".txt" or media_type.startswith("text/plain"):
            return clean_text(content.decode(encoding or "utf-8", errors="replace"))

        raise ValueError(f"неподдерживаемый формат документа: {media_type or extension}")


def _filename_from_disposition(header: str) -> str | None:
    """regulation.gov.ru часто кладёт имя файла только в Content-Disposition."""
    if not header:
        return None
    starred = re.search(r"filename\*=(?:UTF-8''|utf-8'')([^;]+)", header, re.IGNORECASE)
    if starred:
        return unquote(starred.group(1).strip().strip('"'))
    plain = re.search(r'filename="([^"]+)"|filename=([^;]+)', header, re.IGNORECASE)
    if plain:
        return unquote((plain.group(1) or plain.group(2)).strip().strip('"'))
    return None


def _extract_ole_text(content: bytes) -> str:
    """Достаёт читаемый текст из Word 97–2003 без LibreOffice.

    Полный парсер DOC избыточен для снапшота: в OLE почти всегда есть
    последовательности UTF-16LE и cp1251 с телом документа.
    """
    chunks: list[str] = []
    decoded_utf16 = content.decode("utf-16le", errors="ignore")
    chunks.extend(re.findall(r"[\wА-Яа-яЁё«»\"'().,;:%№/\- ]{20,}", decoded_utf16))
    decoded_1251 = content.decode("cp1251", errors="ignore")
    chunks.extend(re.findall(r"[\wА-Яа-яЁё«»\"'().,;:%№/\- ]{20,}", decoded_1251))
    unique: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        normalized = clean_text(chunk)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    if not unique:
        raise ValueError("в OLE-документе не найден читаемый текст")
    return clean_text("\n".join(unique))


register_adapter(WebAdapter())
