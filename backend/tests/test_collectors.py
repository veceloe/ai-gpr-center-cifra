from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import ClassVar

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import src.collectors.base as collector_base
import src.collectors.telegram as telegram_collector
import src.scheduler as scheduler_module
from src.collectors.base import CollectedItem, _upsert_item, collect_active_sources
from src.collectors.rss import RssAdapter
from src.collectors.telegram import TelegramAdapter
from src.collectors.web import WebAdapter
from src.models import Item, ItemType, Source, SourceCategory, SourceType
from src.scheduler import setup_scheduler

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.mark.asyncio
async def test_rss_adapter_loads_full_article(monkeypatch: pytest.MonkeyPatch) -> None:
    real_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed.xml":
            return httpx.Response(200, content=_fixture("rss.xml"))
        if request.url.path == "/news/42":
            return httpx.Response(200, content=_fixture("rss-article.html"))
        return httpx.Response(404)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    source = Source(
        id=1,
        type=SourceType.RSS,
        category=SourceCategory.MEDIA,
        item_type=ItemType.NEWS,
        url="https://media.example/feed.xml",
        title="СМИ",
    )

    items = await RssAdapter().fetch(source, 10)

    assert len(items) == 1
    assert "переходный период" in items[0].raw_text
    assert items[0].external_id == "news-42"


@pytest.mark.asyncio
async def test_regulator_adapter_snapshots_attached_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        fixtures = {
            "/projects": ("regulator-list.html", "text/html; charset=utf-8"),
            "/projects/123": ("regulator-document.html", "text/html; charset=utf-8"),
            "/files/project-123.txt": ("regulator-document.txt", "text/plain; charset=utf-8"),
        }
        if request.url.path not in fixtures:
            return httpx.Response(404)
        name, content_type = fixtures[request.url.path]
        return httpx.Response(200, content=_fixture(name), headers={"content-type": content_type})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    source = Source(
        id=1,
        type=SourceType.WEB,
        category=SourceCategory.REGULATOR,
        item_type=ItemType.ACT,
        url="https://regulator.example/projects",
        title="Регулятор",
    )

    items = await WebAdapter().fetch(source, 10)

    assert len(items) == 1
    assert items[0].url == "https://regulator.example/projects/123"
    assert "Полный текст документа" in items[0].raw_text
    assert "вступает в силу с 1 марта 2027 года" in items[0].raw_text


@pytest.mark.asyncio
async def test_regulation_spa_uses_public_api_and_downloads_stage_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/PublicProjects/GetFiltered"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": "170865",
                            "title": "Проект приказа ФСТЭК",
                            "stage": "Text",
                            "status": "Discussion",
                            "startPublicDiscussion": "2026-09-04T18:41:40",
                        }
                    ]
                },
            )
        if path.endswith("/PublicProjects/GetCardInfo/170865"):
            return httpx.Response(
                200,
                json={
                    "id": 170865,
                    "projectId": "01/02/09-26/00170865",
                    "title": "Проект приказа ФСТЭК",
                    "developerDepartment": {"description": "ФСТЭК России"},
                },
            )
        if path.endswith("/PublicProjects/GetProjectStages/170865"):
            return httpx.Response(
                200,
                json=[
                    {
                        "description": "Общественное обсуждение",
                        "file": {
                            "fileId": "file-1",
                            "description": "project.txt",
                        },
                    }
                ],
            )
        if path.endswith("/Files/GetFile/file-1"):
            return httpx.Response(
                200,
                content="Полный текст проекта приказа.".encode(),
                headers={"content-type": "application/octet-stream"},
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    source = Source(
        id=1,
        type=SourceType.WEB,
        category=SourceCategory.REGULATOR,
        item_type=ItemType.ACT,
        url="https://regulation.gov.ru/projects",
        title="regulation.gov.ru",
    )

    items = await WebAdapter().fetch(source, 5)

    assert len(items) == 1
    assert items[0].url == "https://regulation.gov.ru/projects/170865/"
    assert items[0].external_id == "170865"
    assert "Полный текст проекта приказа" in items[0].raw_text


@pytest.mark.asyncio
async def test_sozd_uses_official_duma_rss_for_bill_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><item>
      <title>О внесении изменений в закон</title>
      <link>https://sozd.duma.gov.ru/bill/123-8</link>
    </item></channel></rss>""".encode()
    page = """<html><main><h1>Законопроект 123-8</h1>
    <p>Карточка законопроекта Государственной Думы.</p>
    <a href="/download/document.txt">Скачать текст законопроекта</a>
    </main></html>""".encode()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.duma.gov.ru":
            return httpx.Response(200, content=rss)
        if request.url.path == "/bill/123-8":
            return httpx.Response(200, content=page)
        if request.url.path == "/download/document.txt":
            return httpx.Response(
                200,
                content="Полный текст законопроекта.".encode(),
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    source = Source(
        id=1,
        type=SourceType.WEB,
        category=SourceCategory.REGULATOR,
        item_type=ItemType.ACT,
        url="https://sozd.duma.gov.ru/oz",
        title="СОЗД",
    )

    items = await WebAdapter().fetch(source, 5)

    assert len(items) == 1
    assert items[0].url == "https://sozd.duma.gov.ru/bill/123-8"
    assert "Полный текст законопроекта" in items[0].raw_text


@pytest.mark.asyncio
async def test_telegram_adapter_uses_last_message_as_min_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMessage:
        def __init__(self) -> None:
            self.id = 42
            self.message = "Новая отраслевая новость"
            self.date = datetime(2026, 9, 5, tzinfo=UTC)

    class FakeClient:
        iter_kwargs: ClassVar[dict] = {}

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def is_user_authorized(self) -> bool:
            return True

        async def get_entity(self, username: str) -> str:
            return username

        async def iter_messages(self, _entity: str, **kwargs):
            self.__class__.iter_kwargs = kwargs
            yield FakeMessage()

    telethon = ModuleType("telethon")
    telethon.TelegramClient = FakeClient
    sessions = ModuleType("telethon.sessions")
    sessions.StringSession = lambda value: value
    types = ModuleType("telethon.tl.types")
    types.Message = FakeMessage
    monkeypatch.setitem(sys.modules, "telethon", telethon)
    monkeypatch.setitem(sys.modules, "telethon.sessions", sessions)
    monkeypatch.setitem(sys.modules, "telethon.tl.types", types)
    monkeypatch.setattr(
        telegram_collector,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_configured=True,
            telegram_string_session="session",
            telegram_api_id=1,
            telegram_api_hash="hash",
            telegram_proxy="",
        ),
    )
    source = Source(
        id=1,
        type=SourceType.TELEGRAM,
        category=SourceCategory.TELEGRAM,
        item_type=ItemType.NEWS,
        url="https://t.me/example",
        title="Telegram",
        last_external_id="41",
    )

    items = await TelegramAdapter().fetch(source, 200)

    assert FakeClient.iter_kwargs == {"limit": 200, "min_id": 41}
    assert items[0].external_id == "42"


@pytest.mark.asyncio
async def test_broken_source_does_not_stop_other_sources(
    session: AsyncSession, source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    source.url = "https://broken.example/rss"
    healthy = Source(
        type=SourceType.RSS,
        category=SourceCategory.MEDIA,
        item_type=ItemType.NEWS,
        url="https://healthy.example/rss",
        title="Рабочий источник",
    )
    session.add(healthy)
    await session.commit()

    class FakeRssAdapter:
        source_type = SourceType.RSS

        async def fetch(self, current: Source, _limit: int) -> list[CollectedItem]:
            if "broken" in current.url:
                raise httpx.ConnectError("source unavailable")
            return [
                CollectedItem(
                    url="https://healthy.example/news/1",
                    title="Новость",
                    raw_text="Полный текст новости из рабочего источника.",
                )
            ]

    monkeypatch.setitem(collector_base._ADAPTERS, SourceType.RSS, FakeRssAdapter())

    results = await collect_active_sources(session, 10)

    assert len(results) == 2
    assert any(result.error for result in results)
    assert any(result.created == 1 for result in results)


@pytest.mark.asyncio
async def test_same_url_updates_hash_without_creating_duplicate(
    session: AsyncSession, source: Source, item: Item
) -> None:
    item.processed_at = datetime(2026, 9, 5, tzinfo=UTC)
    old_hash = item.content_hash

    result = await _upsert_item(
        session,
        source,
        CollectedItem(
            url=item.url,
            title="Обновлённый заголовок",
            raw_text="Новая полная редакция ранее опубликованного материала.",
        ),
    )
    await session.flush()

    count = await session.scalar(select(func.count()).select_from(Item).where(Item.url == item.url))
    assert result == "updated"
    assert count == 1
    assert item.content_hash != old_hash
    assert item.processed_at is None


def test_scheduler_uses_separate_intervals_for_media_and_regulators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: SimpleNamespace(
            poll_interval_media_min=15,
            poll_interval_regulator_min=60,
        ),
    )
    scheduler = setup_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert jobs["collect_media_sources"].trigger.interval.total_seconds() == 15 * 60
    assert jobs["collect_regulator_sources"].trigger.interval.total_seconds() == 60 * 60


def test_document_sniff_reads_ole_without_extension() -> None:
    from src.collectors.web import OLE_MAGIC, WebAdapter

    payload = "Обязательные требования к российским системам условного доступа. "
    ole = OLE_MAGIC + payload.encode("utf-16le")
    text = WebAdapter._extract_document_text(
        ole, "https://regulation.example/file/1", "application/octet-stream", None
    )
    assert "условного доступа" in text


def test_document_sniff_reads_msword_without_filename() -> None:
    from src.collectors.web import OLE_MAGIC, WebAdapter

    payload = "Пояснительная записка к проекту приказа. "
    ole = OLE_MAGIC + payload.encode("utf-16le")
    text = WebAdapter._extract_document_text(
        ole, "https://sozd.example/download/1", "application/msword", None
    )
    assert "Пояснительная записка" in text


def test_filename_from_content_disposition() -> None:
    from src.collectors.web import _filename_from_disposition

    assert _filename_from_disposition(
        "attachment; filename=\"poyasnitelnaya.docx\""
    ) == "poyasnitelnaya.docx"
    assert _filename_from_disposition(
        "attachment; filename*=UTF-8''%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82.doc"
    ) == "проект.doc"
