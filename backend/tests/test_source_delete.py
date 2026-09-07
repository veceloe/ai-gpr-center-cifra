"""Удаление источника — FR-004 и дефект, найденный на демо.

Источник с собранными материалами нельзя стирать из базы: лента потеряет
происхождение материалов. Прежняя реализация вместо удаления дописывала
к названию « (удалён)» — при каждом нажатии заново — и оставляла источник
в списке. Со стороны это выглядело так, будто удаление не работает,
а название бесконечно растёт.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.main import app
from src.db import apply_compat_migrations, get_db
from src.models import Item, Source


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
async def test_deleting_source_with_items_hides_it_without_touching_the_title(
    client: AsyncClient, session: AsyncSession, source: Source
) -> None:
    session.add(
        Item(
            source_id=source.id,
            url="https://example.test/kept",
            title="Материал остаётся в ленте",
            raw_text="Текст",
            content_hash="kept-1",
            published_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    await session.commit()
    original_title = source.title

    for _ in range(3):
        assert (await client.delete(f"/sources/{source.id}")).status_code == 204

    await session.refresh(source)
    assert source.title == original_title, "название не должно обрастать пометками"
    assert source.is_archived is True
    assert source.is_active is False

    listed = (await client.get("/sources")).json()
    assert source.id not in [s["id"] for s in listed], "удалённый источник уходит из списка"

    archived = (await client.get("/sources", params={"archived": True})).json()
    assert source.id in [s["id"] for s in archived], "но остаётся доступен явным запросом"

    kept = await session.scalar(select(Item).where(Item.source_id == source.id))
    assert kept is not None, "материалы сохраняют происхождение — FR-004"


@pytest.mark.asyncio
async def test_deleting_source_without_items_removes_the_row(
    client: AsyncClient, session: AsyncSession, source: Source
) -> None:
    source_id = source.id
    assert (await client.delete(f"/sources/{source_id}")).status_code == 204
    assert await session.get(Source, source_id) is None


@pytest.mark.asyncio
async def test_migration_cleans_titles_left_by_the_old_delete(
    session: AsyncSession, source: Source
) -> None:
    """Названия, уже испорченные прежней версией, чинятся при запуске."""
    await session.execute(
        text("UPDATE sources SET title = :t WHERE id = :i"),
        {"t": "Ведомости (удалён) (удалён) (удалён)", "i": source.id},
    )
    # Возвращаем базу к состоянию до миграции: индекс снимаем первым, иначе
    # SQLite не даст удалить колонку, на которую он ссылается.
    await session.execute(text("DROP INDEX IF EXISTS ix_sources_is_archived"))
    await session.execute(text("ALTER TABLE sources DROP COLUMN is_archived"))
    await session.commit()

    await apply_compat_migrations(await session.connection())

    row = (
        await session.execute(
            text("SELECT title, is_archived FROM sources WHERE id = :i"), {"i": source.id}
        )
    ).one()
    assert row[0] == "Ведомости", "накопленные пометки сняты"
    assert row[1] == 1, "такой источник переведён в архив"
