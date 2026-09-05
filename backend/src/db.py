"""Подключение к базе и фабрика сессий."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config import DATA_DIR, get_settings
from src.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def register_sqlite_functions(engine: AsyncEngine) -> None:
    """Подменяет SQLite-функцию lower() питоновской.

    Встроенная умеет только ASCII, поэтому поиск «маркировка» не находил
    «Маркировка» — на русскоязычном корпусе это делало поиск бесполезным.
    SQLAlchemy компилирует ilike на SQLite как lower(a) LIKE lower(b),
    так что подмены достаточно, менять запросы не нужно.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _register(dbapi_connection, _record) -> None:  # pragma: no cover - callback драйвера
        dbapi_connection.create_function(
            "lower", 1, lambda value: value.lower() if isinstance(value, str) else value
        )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(
            get_settings().database_url,
            echo=False,
            # ensure_ascii=False обязателен: иначе кириллица в JSON-колонках (теги,
            # сущности саммари) хранится экранированной как \uXXXX, и поиск по ней
            # не находит ничего. Заодно база остаётся читаемой глазами.
            json_serializer=lambda value: json.dumps(value, ensure_ascii=False),
        )
        register_sqlite_functions(_engine)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _session_factory


async def apply_compat_migrations(conn) -> None:
    """Точечные правки существующего app.db: Alembic в прототипе нет."""
    columns = {
        row[1] for row in (await conn.execute(text("PRAGMA table_info(sources)"))).all()
    }
    if "item_type" not in columns:
        await conn.execute(
            text(
                "ALTER TABLE sources ADD COLUMN item_type VARCHAR(16) "
                "NOT NULL DEFAULT 'news'"
            )
        )
        await conn.execute(
            text("UPDATE sources SET item_type = 'act' WHERE category = 'regulator'")
        )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_sources_item_type ON sources (item_type)")
    )
    story_columns = {
        row[1] for row in (await conn.execute(text("PRAGMA table_info(stories)"))).all()
    }
    if story_columns and "item_count" not in story_columns:
        await conn.execute(
            text("ALTER TABLE stories ADD COLUMN item_count INTEGER NOT NULL DEFAULT 0")
        )
        await conn.execute(
            text(
                """
                UPDATE stories
                SET item_count = (
                    SELECT COUNT(*) FROM items WHERE items.story_id = stories.id
                )
                """
            )
        )
    item_columns = {
        row[1] for row in (await conn.execute(text("PRAGMA table_info(items)"))).all()
    }
    if "act_identifier" not in item_columns:
        await conn.execute(text("ALTER TABLE items ADD COLUMN act_identifier VARCHAR(512)"))
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_items_act_identifier ON items (act_identifier)")
    )
    # Материалы, собранные до появления Source.item_type, копируют тип источника.
    await conn.execute(
        text(
            """
            UPDATE items
            SET item_type = (
                SELECT sources.item_type FROM sources WHERE sources.id = items.source_id
            )
            WHERE EXISTS (
                SELECT 1 FROM sources
                WHERE sources.id = items.source_id
                  AND sources.item_type IS NOT NULL
                  AND sources.item_type != items.item_type
            )
            """
        )
    )


async def init_db() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_compat_migrations(conn)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI: сессия на запрос."""
    async with get_session_factory()() as session:
        yield session


def reset_engine() -> None:
    """Сбрасывает кеш движка — нужно тестам, которые меняют DATABASE_URL."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
