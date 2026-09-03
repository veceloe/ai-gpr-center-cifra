from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db import register_sqlite_functions
from src.models import Base, CompanyProfile, Item, Source, SourceCategory, SourceType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        json_serializer=lambda value: json.dumps(value, ensure_ascii=False),
    )
    register_sqlite_functions(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def profile(session: AsyncSession) -> CompanyProfile:
    profile = CompanyProfile(
        slug="test-co",
        name="Тестовая компания",
        industry="Разработка ПО для платного телевидения",
        products=["Системы условного доступа"],
        regimes=["ИТ-аккредитация"],
        risk_areas=["Реестр российского ПО"],
        growth_areas=["Гранты для ИТ"],
        competitors=["Другие вендоры CAS"],
        noise_markers=["Агрономия"],
        is_active=True,
    )
    session.add(profile)
    await session.commit()
    return profile


@pytest_asyncio.fixture
async def source(session: AsyncSession) -> Source:
    src = Source(
        type=SourceType.RSS,
        category=SourceCategory.MEDIA,
        url="https://example.test/rss",
        title="Тестовый источник",
    )
    session.add(src)
    await session.commit()
    return src


@pytest_asyncio.fixture
async def item(session: AsyncSession, source: Source) -> Item:
    obj = Item(
        source_id=source.id,
        url="https://example.test/news/1",
        title="Тестовая публикация",
        raw_text=(
            "Государственная Дума приняла закон о поддержке технологий искусственного "
            "интеллекта. Документ вводит режим для больших фундаментальных моделей "
            "с числом параметров не менее одного миллиарда. Маркировка контента "
            "становится обязательной с 1 марта 2027 года."
        ),
        content_hash="test-hash",
        published_at=datetime(2026, 9, 1, tzinfo=UTC),
        tags=[],
    )
    session.add(obj)
    await session.commit()
    return obj
