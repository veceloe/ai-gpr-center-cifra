"""Интерфейс источника и сохранение собранного — FR-001…FR-008.

Разные типы источников отличаются только способом получения списка материалов.
Всё остальное — дедупликация по URL, версионирование текста, фиксация ошибок —
общее и живёт здесь.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Item, Source, SourceType
from src.pipeline.normalize import clean_text, content_hash, detect_partial_text, resolve_published_at

logger = logging.getLogger(__name__)


@dataclass
class CollectedItem:
    """Материал в том виде, в каком его отдал источник."""

    url: str
    title: str
    raw_text: str
    published_at: datetime | None = None
    # Внешний идентификатор для инкрементального сбора: message_id у Telegram.
    external_id: str | None = None


@dataclass
class CollectResult:
    source_id: int
    fetched: int = 0
    created: int = 0
    updated: int = 0
    error: str | None = None


class SourceAdapter(Protocol):
    source_type: SourceType

    async def fetch(self, source: Source, limit: int) -> list[CollectedItem]: ...


_ADAPTERS: dict[SourceType, SourceAdapter] = {}


def register_adapter(adapter: SourceAdapter) -> SourceAdapter:
    _ADAPTERS[adapter.source_type] = adapter
    return adapter


def get_adapter(source_type: SourceType) -> SourceAdapter:
    try:
        return _ADAPTERS[source_type]
    except KeyError as exc:
        raise LookupError(f"нет адаптера для типа источника {source_type}") from exc


async def collect_source(session: AsyncSession, source: Source, limit: int) -> CollectResult:
    """Собирает один источник. Ошибка фиксируется в источнике и не поднимается выше.

    Это FR-008: недоступный источник не должен останавливать сбор из остальных.
    """
    result = CollectResult(source_id=source.id)
    try:
        adapter = get_adapter(source.type)
        collected = await adapter.fetch(source, limit)
    except Exception as exc:
        source.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
        source.last_polled_at = datetime.now(UTC)
        result.error = source.last_error
        logger.warning("Источник %s (%s): %s", source.id, source.title, result.error)
        await session.flush()
        return result

    result.fetched = len(collected)
    max_external_id = source.last_external_id

    for candidate in collected:
        stored = await _upsert_item(session, source, candidate)
        if stored == "created":
            result.created += 1
        elif stored == "updated":
            result.updated += 1
        if candidate.external_id and (max_external_id is None or _gt(candidate.external_id, max_external_id)):
            max_external_id = candidate.external_id

    source.last_external_id = max_external_id
    source.last_polled_at = datetime.now(UTC)
    source.last_error = None
    await session.flush()

    logger.info(
        "Источник %s: получено %s, новых %s, обновлено %s",
        source.title,
        result.fetched,
        result.created,
        result.updated,
    )
    return result


def _gt(a: str, b: str) -> bool:
    """Сравнение внешних идентификаторов: числовые — как числа, иначе как строки."""
    if a.isdigit() and b.isdigit():
        return int(a) > int(b)
    return a > b


async def _upsert_item(session: AsyncSession, source: Source, candidate: CollectedItem) -> str:
    """Дедупликация по URL — FR-007.

    Тот же URL с изменившимся текстом не создаёт дубликат, но обновляет содержимое
    и сбрасывает признак обработки: материал переоценивается.
    """
    text = clean_text(candidate.raw_text)
    if not text:
        return "skipped"

    digest = content_hash(text)
    existing = (
        await session.execute(select(Item).where(Item.url == candidate.url))
    ).scalar_one_or_none()

    if existing is not None:
        if existing.content_hash == digest:
            return "unchanged"
        existing.raw_text = text
        existing.content_hash = digest
        existing.title = candidate.title or existing.title
        existing.is_partial_text = detect_partial_text(text)
        existing.processed_at = None  # текст изменился — нужна переобработка
        return "updated"

    published_at, is_approx = resolve_published_at(candidate.published_at)
    session.add(
        Item(
            source_id=source.id,
            url=candidate.url,
            title=candidate.title or candidate.url,
            raw_text=text,
            content_hash=digest,
            published_at=published_at,
            published_at_is_approx=is_approx,
            is_partial_text=detect_partial_text(text),
            tags=[],
        )
    )
    return "created"


async def collect_active_sources(session: AsyncSession, limit_per_source: int) -> list[CollectResult]:
    sources = list(
        (await session.execute(select(Source).where(Source.is_active.is_(True)))).scalars().all()
    )
    results = []
    for source in sources:
        results.append(await collect_source(session, source, limit_per_source))
        await session.commit()
    return results
