"""Коллектор СОЗД — задача T064, research R-04.

Разбор проверяется на сохранённых снимках: живой сайт из части сетей недоступен,
а парсер, который нельзя прогнать, — это парсер, про который мы ничего не знаем.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from src.collectors.sozd import (
    SozdAdapter,
    detect_stage,
    extract_bill_number,
    extract_last_event_date,
    extract_title,
)
from src.models import ActStage, Source, SourceCategory, SourceType
from src.pipeline.normalize import extract_from_html

FIXTURES = Path(__file__).parent / "fixtures"
BILL_HTML = (FIXTURES / "sozd-bill.html").read_text(encoding="utf-8")
LIST_HTML = (FIXTURES / "sozd-list.html").read_text(encoding="utf-8")


class TestBillNumber:
    def test_extracted_from_href(self) -> None:
        assert extract_bill_number('<a href="/bill/1215252-8">текст</a>') == "1215252-8"

    def test_extracted_from_plain_text(self) -> None:
        assert extract_bill_number("Законопроект № 1271570-8 внесён") == "1271570-8"

    def test_absent_gives_none(self) -> None:
        assert extract_bill_number("никаких номеров тут нет") is None


class TestStageDetection:
    def test_latest_stage_wins(self) -> None:
        """Карточка содержит всю историю — нужна текущая стадия, а не первая."""
        assert detect_stage(BILL_HTML) is ActStage.READINGS

    def test_submitted_only(self) -> None:
        assert detect_stage("Законопроект внесён в ГД 10.07.2026") is ActStage.SUBMITTED

    def test_in_force_beats_readings(self) -> None:
        text = "Первое чтение состоялось. Второе чтение. Опубликован 01.09.2026."
        assert detect_stage(text) is ActStage.IN_FORCE

    def test_unknown_gives_none(self) -> None:
        assert detect_stage("страница про погоду") is None


class TestDates:
    def test_latest_date_taken(self) -> None:
        plain = extract_from_html(BILL_HTML)
        assert extract_last_event_date(plain) == date(2026, 10, 14)

    def test_impossible_dates_ignored(self) -> None:
        assert extract_last_event_date("32.13.2026 и 01.02.1970") is None

    def test_far_future_ignored(self) -> None:
        """Опечатка в году не должна становиться датой последнего события."""
        assert extract_last_event_date("01.01.2099 и 05.03.2026") == date(2026, 3, 5)


class TestTitle:
    def test_taken_from_page_title_without_site_name(self) -> None:
        plain = extract_from_html(BILL_HTML)
        title = extract_title(BILL_HTML, plain, "1215252-8")
        assert "О внесении изменений" in title
        assert "СОЗД" not in title

    def test_fallback_when_no_title_tag(self) -> None:
        html = "<body><p>Короткое</p><p>Достаточно длинная строка про законопроект связи</p></body>"
        plain = extract_from_html(html)
        assert "законопроект связи" in extract_title(html, plain, "1215252-8")


class TestListParsing:
    def test_bill_numbers_deduplicated_and_ordered(self) -> None:
        assert SozdAdapter()._bill_numbers(LIST_HTML, 10) == [
            "1215252-8",
            "1271570-8",
            "1286413-8",
        ]

    def test_limit_respected(self) -> None:
        assert len(SozdAdapter()._bill_numbers(LIST_HTML, 2)) == 2

    def test_foreign_links_ignored(self) -> None:
        numbers = SozdAdapter()._bill_numbers(LIST_HTML, 10)
        assert all("-" in n for n in numbers)


@pytest.mark.asyncio
async def test_fetch_builds_items_from_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сквозной разбор на снимках: список → карточки → материалы."""
    source = Source(
        id=1,
        type=SourceType.SOZD,
        category=SourceCategory.REGULATOR,
        url="https://sozd.duma.gov.ru/oz",
        title="СОЗД",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oz":
            return httpx.Response(200, html=LIST_HTML)
        if request.url.path.startswith("/bill/"):
            return httpx.Response(200, html=BILL_HTML)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)

    items = await SozdAdapter().fetch(source, limit=3)

    assert len(items) == 3
    first = items[0]
    assert first.url == "https://sozd.duma.gov.ru/bill/1215252-8"
    assert first.external_id == "1215252-8"
    # Стадия и дата попадают в начало текста: юридическая сила (К2) выводится из них.
    assert "Текущая стадия: рассмотрение в чтениях" in first.raw_text
    assert "14.10.2026" in first.raw_text
    assert first.published_at is not None


@pytest.mark.asyncio
async def test_empty_list_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустая выдача — это не тихий ноль, а понятная ошибка в статусе источника."""
    source = Source(
        id=1,
        type=SourceType.SOZD,
        category=SourceCategory.REGULATOR,
        url="https://sozd.duma.gov.ru/oz",
        title="СОЗД",
    )
    transport = httpx.MockTransport(lambda r: httpx.Response(200, html="<html><body>пусто</body></html>"))
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **kw: original(*a, **{**kw, "transport": transport})
    )

    with pytest.raises(ValueError, match="не найдено ссылок"):
        await SozdAdapter().fetch(source, limit=5)
