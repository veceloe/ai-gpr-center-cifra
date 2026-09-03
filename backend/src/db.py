"""Подключение к базе и фабрика сессий."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from sqlalchemy import event
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


async def init_db() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI: сессия на запрос."""
    async with get_session_factory()() as session:
        yield session


def reset_engine() -> None:
    """Сбрасывает кеш движка — нужно тестам, которые меняют DATABASE_URL."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
