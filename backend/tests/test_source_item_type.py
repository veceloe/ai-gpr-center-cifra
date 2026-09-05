from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.base import CollectedItem, _upsert_item
from src.db import apply_compat_migrations
from src.models import Item, ItemType, Source


@pytest.mark.asyncio
async def test_collected_item_inherits_source_item_type(
    session: AsyncSession, source: Source
) -> None:
    source.item_type = ItemType.ACT
    candidate = CollectedItem(
        url="https://duma.example/document/1",
        title="Проект федерального закона",
        raw_text="Официальный текст проекта федерального закона.",
    )

    result = await _upsert_item(session, source, candidate)
    await session.flush()

    stored = await session.scalar(select(Item).where(Item.url == candidate.url))
    assert result == "created"
    assert stored is not None
    assert stored.item_type == ItemType.ACT


@pytest.mark.asyncio
async def test_init_db_realigns_item_type_to_source(
    session: AsyncSession, source: Source
) -> None:
    """Старые карточки, собранные до Source.item_type, получают тип источника."""
    source.item_type = ItemType.ACT
    session.add(
        Item(
            source_id=source.id,
            url="https://legacy.example/old",
            title="Старый материал",
            raw_text="Текст до смены контракта.",
            content_hash="legacy-type",
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            item_type=ItemType.NEWS,
            tags=[],
        )
    )
    await session.commit()

    await apply_compat_migrations(await session.connection())
    stored = await session.scalar(select(Item).where(Item.url == "https://legacy.example/old"))
    assert stored is not None
    await session.refresh(stored)
    assert stored.item_type == ItemType.ACT
