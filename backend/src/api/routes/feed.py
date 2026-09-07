"""Лента — FR-020, FR-021, FR-022.

Сортировка по убыванию индекса влияния: специалист начинает день с того, что
сильнее всего касается его компании, а не с того, что опубликовано позже.
Нерелевантное в основную ленту не попадает, но остаётся доступным отдельно (FR-018).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import FeedResponse, item_card
from src.db import get_db
from src.models import Assessment, Item, Revision, Summary

router = APIRouter(tags=["feed"])

MAX_LIMIT = 200


def _apply_filters(
    stmt: Select,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    source_id: int | None,
    item_type: str | None,
    topic: str | None,
    category: str | None,
    query: str | None,
    include_irrelevant: bool,
    include_hidden: bool,
) -> Select:
    if date_from is not None:
        stmt = stmt.where(Item.published_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Item.published_at <= date_to)
    if source_id is not None:
        stmt = stmt.where(Item.source_id == source_id)
    if item_type:
        stmt = stmt.where(Item.item_type == item_type)
    if topic:
        stmt = stmt.where(Item.topic == topic)
    if category:
        stmt = stmt.where(Assessment.final_category == category)
    if not include_hidden:
        stmt = stmt.where(Item.is_hidden.is_(False))
    if not include_irrelevant:
        # Материал без оценки показываем: он ещё не признан шумом, просто не обработан.
        stmt = stmt.where(or_(Item.is_relevant.is_(True), Item.is_relevant.is_(None)))
    if query:
        pattern = f"%{query.strip()}%"
        # FR-022: поиск по тексту, тегам и извлечённым сущностям. Теги и сущности
        # хранятся как JSON, поэтому приводим их к тексту — на объёмах прототипа
        # этого достаточно, полнотекстовый индекс избыточен.
        stmt = stmt.where(
            or_(
                Item.title.ilike(pattern),
                Item.raw_text.ilike(pattern),
                Item.user_note.ilike(pattern),
                cast(Item.tags, Text).ilike(pattern),
                Summary.text.ilike(pattern),
                cast(Summary.entities, Text).ilike(pattern),
            )
        )
    return stmt


def _hide_story_duplicates(stmt: Select) -> Select:
    """В ленте одна карточка на событие — остальные источники живут в /stories/{id}.

    Представитель — материал с наибольшим индексом влияния: лента сортируется
    по воздействию, и прятать более сильную карточку за более ранний id нельзя.
    """
    ranked = (
        select(
            Item.id,
            func.row_number()
            .over(
                partition_by=Item.story_id,
                order_by=(Assessment.index_value.desc().nullslast(), Item.id.asc()),
            )
            .label("rn"),
        )
        .outerjoin(Assessment, (Assessment.item_id == Item.id) & Assessment.is_current.is_(True))
        .where(Item.story_id.isnot(None))
        .subquery()
    )
    representatives = select(ranked.c.id).where(ranked.c.rn == 1)
    return stmt.where(or_(Item.story_id.is_(None), Item.id.in_(representatives)))


def _hide_act_duplicates(stmt: Select) -> Select:
    """В ленте одна карточка на акт — остальные публикации живут в досье.

    Правило то же, что для сюжетов: одна поправка обсуждается сразу
    несколькими изданиями и регуляторными площадками, и без схлопывания
    она занимает пол-экрана ленты, вытесняя всё остальное.

    Представитель — материал с наибольшим индексом влияния, а не самый ранний:
    лента отсортирована по воздействию, и прятать более сильную карточку
    за более ранний идентификатор нельзя.
    """
    ranked = (
        select(
            Item.id,
            func.row_number()
            .over(
                partition_by=Item.act_id,
                order_by=(Assessment.index_value.desc().nullslast(), Item.id.asc()),
            )
            .label("rn"),
        )
        .outerjoin(Assessment, (Assessment.item_id == Item.id) & Assessment.is_current.is_(True))
        .where(Item.act_id.isnot(None))
        .subquery()
    )
    representatives = select(ranked.c.id).where(ranked.c.rn == 1)
    return stmt.where(or_(Item.act_id.is_(None), Item.id.in_(representatives)))


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    db: Annotated[AsyncSession, Depends(get_db)],
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source_id: int | None = None,
    item_type: Annotated[str | None, Query(pattern="^(news|act)$")] = None,
    topic: Annotated[
        str | None, Query(pattern="^(regulatory|reputation|competitors|trends)$")
    ] = None,
    category: str | None = None,
    q: Annotated[str | None, Query(description="поиск по тексту, тегам и сущностям")] = None,
    include_irrelevant: bool = False,
    include_hidden: bool = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FeedResponse:
    filters = {
        "date_from": date_from,
        "date_to": date_to,
        "source_id": source_id,
        "item_type": item_type,
        "topic": topic,
        "category": category,
        "query": q,
        "include_irrelevant": include_irrelevant,
        "include_hidden": include_hidden,
    }

    base = (
        select(Item)
        .outerjoin(Assessment, (Assessment.item_id == Item.id) & Assessment.is_current.is_(True))
        .outerjoin(Summary, (Summary.item_id == Item.id) & Summary.is_current.is_(True))
        .options(
            selectinload(Item.source),
            selectinload(Item.summaries),
            selectinload(Item.assessments),
            selectinload(Item.story),
        )
    )
    stmt = _hide_act_duplicates(_hide_story_duplicates(_apply_filters(base, **filters)))

    count_base = _apply_filters(
        select(func.count(func.distinct(Item.id)))
        .outerjoin(Assessment, (Assessment.item_id == Item.id) & Assessment.is_current.is_(True))
        .outerjoin(Summary, (Summary.item_id == Item.id) & Summary.is_current.is_(True)),
        **filters,
    )
    count_stmt = _hide_act_duplicates(_hide_story_duplicates(count_base))
    total = (await db.execute(count_stmt)).scalar() or 0

    # Материалы без оценки не должны вытеснять оценённые в начало ленты.
    stmt = stmt.order_by(
        Assessment.index_value.desc().nullslast(), Item.published_at.desc()
    ).limit(limit).offset(offset)
    items = list((await db.execute(stmt)).unique().scalars().all())

    edited_ids = set()
    if items:
        edited = await db.execute(
            select(Revision.entity_id).where(
                Revision.entity_type.in_(("item", "summary", "assessment")),
                Revision.entity_id.in_([i.id for i in items]),
            )
        )
        edited_ids = set(edited.scalars().all())

    return FeedResponse(
        items=[item_card(item, is_edited=item.id in edited_ids) for item in items],
        total=total,
    )
