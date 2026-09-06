from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.cli import SEED_SOURCES, _initialize_database
from src.config import get_settings
from src.db import get_engine, get_session_factory, reset_engine
from src.models import CompanyProfile, Source, Story
from src.scoring.config import load_scoring_config


def test_scoring_config_is_valid() -> None:
    config = load_scoring_config()

    assert [criterion.code for criterion in config.npa.criteria] == [
        "К1",
        "К2",
        "К3",
        "К4",
        "К5",
        "К6",
    ]
    assert [criterion.code for criterion in config.news.criteria] == ["Н1", "Н2", "Н3", "Н4"]


@pytest.mark.asyncio
async def test_init_db_creates_schema_and_seeds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database_path = tmp_path / "initialized.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    get_settings.cache_clear()
    reset_engine()

    try:
        await _initialize_database()

        async with get_session_factory()() as session:
            source_count = await session.scalar(select(func.count()).select_from(Source))
            profiles = (await session.scalars(select(CompanyProfile))).all()

            assert source_count == 5 == len(SEED_SOURCES)
            # СОЗД — отдельный тип источника, а не обычная веб-страница: у него
            # свой разбор по номеру законопроекта и стадиям (T064).
            assert {source.type for source in (await session.scalars(select(Source))).all()} == {
                "rss",
                "sozd",
                "telegram",
                "web",
            }
            assert sum(profile.is_active for profile in profiles) == 1

            story = Story(canonical_title="Событие", fact_summary="Факт")
            session.add(story)
            await session.flush()
            assert story.item_count == 0
    finally:
        await get_engine().dispose()
        reset_engine()
        get_settings.cache_clear()
