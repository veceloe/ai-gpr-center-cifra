"""Минимальные маршруты досье НПА — T059, T060."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.main import app
from src.db import get_db
from src.models import Item, ItemType, Source


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_track_as_act_creates_dossier_and_get_routes_return_it(
    client: AsyncClient, session: AsyncSession, source: Source
) -> None:
    item = Item(
        source_id=source.id,
        url="https://duma.example/bill/243",
        title="Законопроект о поддержке технологий ИИ",
        raw_text="Текст проекта федерального закона.",
        content_hash="act-api",
        item_type=ItemType.ACT,
        act_identifier="Законопроект № 243-ФЗ",
        published_at=datetime(2026, 9, 1, tzinfo=UTC),
        tags=[],
    )
    session.add(item)
    await session.commit()

    created = await client.post(f"/items/{item.id}/track-as-act")
    assert created.status_code == 201
    body = created.json()
    assert body["act_identifier"] == "Законопроект № 243-ФЗ"
    assert body["doc_type"] == "НПА"
    assert body["stage"] == "announcement"
    assert body["is_tracked"] is True
    assert body["linked_items"][0]["id"] == item.id
    assert body["timeline"][0]["event_type"] == "other"
    assert body["timeline"][0]["source_item_id"] == item.id

    listed = (await client.get("/acts")).json()
    assert [act["act_identifier"] for act in listed] == ["Законопроект № 243-ФЗ"]

    detail = (await client.get(f"/acts/{body['id']}")).json()
    assert detail["linked_items"][0]["act_id"] == body["id"]
    assert detail["timeline"][0]["document_url"] == item.url


@pytest.mark.asyncio
async def test_track_as_act_uses_url_hash_when_identifier_is_missing(
    client: AsyncClient, session: AsyncSession, source: Source
) -> None:
    item = Item(
        source_id=source.id,
        url="https://duma.example/bill/no-id",
        title="Проект без номера",
        raw_text="Текст проекта без номера.",
        content_hash="act-api-no-id",
        item_type=ItemType.ACT,
        published_at=datetime(2026, 9, 1, tzinfo=UTC),
        tags=[],
    )
    session.add(item)
    await session.commit()

    response = await client.post(f"/items/{item.id}/track-as-act")
    assert response.status_code == 201
    body = response.json()
    assert body["act_identifier"].startswith("url:")
    assert body["linked_items"][0]["id"] == item.id
