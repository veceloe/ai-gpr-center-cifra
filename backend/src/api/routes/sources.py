"""Управление источниками — FR-003, FR-004, FR-005.

Обязательное требование заказчика: пользователь добавляет источник сам и получает
из него материалы без обращения к разработчику (SC-010).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import SourceCreate, SourceOut, SourceUpdate
from src.config import get_settings
from src.db import get_db, get_session_factory
from src.models import Item, Source, SourceCategory, SourceType

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sources"])

# Категория по умолчанию выводится из типа: Telegram — всегда telegram, RSS — СМИ,
# страница — как правило регулятор. Пользователь может переопределить.
DEFAULT_CATEGORY = {
    SourceType.RSS: SourceCategory.MEDIA,
    SourceType.WEB: SourceCategory.REGULATOR,
    SourceType.TELEGRAM: SourceCategory.TELEGRAM,
    SourceType.MANUAL: SourceCategory.MEDIA,
}


def _out(source: Source, item_count: int = 0) -> SourceOut:
    return SourceOut(
        id=source.id,
        type=str(source.type),
        category=str(source.category),
        url=source.url,
        title=source.title,
        is_active=source.is_active,
        poll_interval_min=source.poll_interval_min,
        last_polled_at=source.last_polled_at,
        last_error=source.last_error,
        item_count=item_count,
    )


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(db: Annotated[AsyncSession, Depends(get_db)]) -> list[SourceOut]:
    counts = dict(
        (await db.execute(select(Item.source_id, func.count(Item.id)).group_by(Item.source_id))).all()
    )
    sources = list((await db.execute(select(Source).order_by(Source.id))).scalars().all())
    return [_out(s, counts.get(s.id, 0)) for s in sources]


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> SourceOut:
    try:
        source_type = SourceType(payload.type)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Неизвестный тип источника: {payload.type}"
        ) from exc

    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL не задан")
    if (await db.execute(select(Source).where(Source.url == url))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Источник с таким URL уже есть")

    category = SourceCategory(payload.category) if payload.category else DEFAULT_CATEGORY[source_type]
    settings = get_settings()
    interval = (
        settings.poll_interval_regulator_min
        if category is SourceCategory.REGULATOR
        else settings.poll_interval_media_min
    )

    source = Source(
        type=source_type,
        category=category,
        url=url,
        title=(payload.title or url).strip(),
        poll_interval_min=interval,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return _out(source)


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: int, payload: SourceUpdate, db: Annotated[AsyncSession, Depends(get_db)]
) -> SourceOut:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    data = payload.model_dump(exclude_unset=True)
    if data.get("title"):
        source.title = data["title"]
    if "is_active" in data and data["is_active"] is not None:
        source.is_active = data["is_active"]
    if data.get("poll_interval_min"):
        source.poll_interval_min = data["poll_interval_min"]

    await db.commit()
    await db.refresh(source)
    return _out(source)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    """Удаление источника не удаляет собранные материалы — FR-004."""
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    linked = (
        await db.execute(select(func.count(Item.id)).where(Item.source_id == source_id))
    ).scalar() or 0
    if linked:
        # Материалы должны сохранить связь с источником, поэтому вместо удаления —
        # деактивация. Иначе лента потеряет происхождение материалов.
        source.is_active = False
        source.title = f"{source.title} (удалён)"
        await db.commit()
        return
    await db.delete(source)
    await db.commit()


async def _collect_one(source_id: int) -> None:
    """Фоновый сбор: HTTP-ответ не должен ждать сети источника."""
    from src.collectors import collect_source

    settings = get_settings()
    async with get_session_factory()() as session:
        source = await session.get(Source, source_id)
        if source is None:  # pragma: no cover - источник удалили между запросами
            return
        await collect_source(session, source, settings.fetch_limit_per_source)
        await session.commit()


@router.post("/sources/{source_id}/collect", status_code=status.HTTP_202_ACCEPTED)
async def collect_now(
    source_id: int,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Немедленный запуск сбора — нужен на демонстрации, чтобы не ждать расписания."""
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    background.add_task(_collect_one, source_id)
    return {"status": "accepted", "source": source.title}
