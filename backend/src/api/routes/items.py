"""Карточка материала и ручное управление — FR-009, FR-023…FR-025, FR-040…FR-045."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    AssessmentOut,
    AssessmentPatch,
    HideRequest,
    ItemCreate,
    ItemDetailOut,
    ItemPatch,
    assessment_out,
    item_detail,
)
from src.db import get_db
from src.models import (
    Assessment,
    Author,
    Item,
    ItemType,
    Revision,
    Source,
    SourceCategory,
    SourceType,
    Summary,
)
from src.pipeline.normalize import clean_text, content_hash, detect_partial_text
from src.scoring import ScoringError, get_scoring_config
from src.scoring import score as compute_score

router = APIRouter(tags=["items"])

MANUAL_SOURCE_URL = "internal://manual"


async def _load_item(db: AsyncSession, item_id: int) -> Item:
    stmt = (
        select(Item)
        .where(Item.id == item_id)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Item.source),
            selectinload(Item.summaries),
            selectinload(Item.assessments),
            selectinload(Item.story),
        )
    )
    item = (await db.execute(stmt)).unique().scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


async def _revisions(db: AsyncSession, item_id: int) -> list[Revision]:
    return list(
        (
            await db.execute(
                select(Revision)
                .where(
                    Revision.entity_type.in_(("item", "summary", "assessment")),
                    Revision.entity_id == item_id,
                )
                .order_by(Revision.created_at.desc(), Revision.id.desc())
            )
        )
        .scalars()
        .all()
    )


def _log(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    field: str,
    old: object,
    new: object,
    reason: str | None = None,
) -> None:
    """Запись в журнал правок — FR-042.

    Она же защищает поле от автоматической переобработки (FR-043): пайплайн
    пропускает поля, у которых есть правка с author != ai.
    """
    db.add(
        Revision(
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            old_value=old,
            new_value=new,
            author=Author.HUMAN,
            reason=reason,
        )
    )


@router.get("/items/{item_id}", response_model=ItemDetailOut)
async def get_item(item_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> ItemDetailOut:
    item = await _load_item(db, item_id)
    revisions = await _revisions(db, item_id)
    return item_detail(item, is_edited=bool(revisions), revisions=revisions)


@router.post("/items", response_model=ItemDetailOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> ItemDetailOut:
    """Ручное добавление материала — FR-009. Проходит ту же обработку, что собранное."""
    source = (
        await db.execute(select(Source).where(Source.url == MANUAL_SOURCE_URL))
    ).scalar_one_or_none()
    if source is None:
        source = Source(
            type=SourceType.MANUAL,
            category=SourceCategory.MEDIA,
            item_type=ItemType.NEWS,
            url=MANUAL_SOURCE_URL,
            title="Добавлено вручную",
            is_active=False,
        )
        db.add(source)
        await db.flush()

    text = clean_text(payload.raw_text)
    if not text:
        raise HTTPException(status_code=422, detail="Текст материала пуст")

    url = payload.url or f"{MANUAL_SOURCE_URL}/{hashlib.sha256(text.encode()).hexdigest()[:16]}"
    if (await db.execute(select(Item).where(Item.url == url))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Материал с таким URL уже есть")

    published_at = payload.published_at or datetime.now(UTC)
    item = Item(
        source_id=source.id,
        url=url,
        title=payload.title.strip() or url,
        raw_text=text,
        content_hash=content_hash(text),
        item_type=source.item_type,
        published_at=published_at,
        published_at_is_approx=payload.published_at is None,
        is_partial_text=detect_partial_text(text),
        tags=[],
    )
    db.add(item)
    await db.commit()

    return item_detail(await _load_item(db, item.id))


@router.patch("/items/{item_id}", response_model=ItemDetailOut)
async def patch_item(
    item_id: int, payload: ItemPatch, db: Annotated[AsyncSession, Depends(get_db)]
) -> ItemDetailOut:
    """Правка полей. Машинная версия сохраняется, правка не затирается (FR-042, FR-043)."""
    item = await _load_item(db, item_id)
    data = payload.model_dump(exclude_unset=True)

    if "title" in data and data["title"] is not None:
        _log(db, "item", item.id, "title", item.title, data["title"])
        item.title = data["title"]

    if "topic" in data and data["topic"] is not None:
        _log(db, "item", item.id, "topic", str(item.topic) if item.topic else None, data["topic"])
        item.topic = data["topic"]

    if "tags" in data and data["tags"] is not None:
        _log(db, "item", item.id, "tags", item.tags, data["tags"])
        item.tags = data["tags"]

    if "user_note" in data:
        _log(db, "item", item.id, "user_note", item.user_note, data["user_note"])
        item.user_note = data["user_note"]

    if "summary" in data and data["summary"] is not None:
        current = item.current_summary
        for existing in item.summaries:
            existing.is_current = False
        # Правка саммари — новая версия с авторством человека. Машинная остаётся
        # в истории: пользователь должен иметь возможность сравнить.
        item.summaries.append(
            Summary(
                text=data["summary"],
                claims=current.claims if current else [],
                entities=current.entities if current else {},
                author=Author.HUMAN,
                is_current=True,
            )
        )
        _log(db, "summary", item.id, "text", current.text if current else None, data["summary"])

    await db.commit()
    return item_detail(
        await _load_item(db, item_id),
        is_edited=True,
        revisions=await _revisions(db, item_id),
    )


@router.patch("/items/{item_id}/assessment", response_model=AssessmentOut)
async def patch_assessment(
    item_id: int, payload: AssessmentPatch, db: Annotated[AsyncSession, Depends(get_db)]
) -> AssessmentOut:
    """Правка баллов с немедленным пересчётом индекса — FR-041.

    Пользователь исправляет один балл, а не отвергает оценку целиком. Каждая такая
    правка — эталонная метка: расхождение машина/человек пополняет eval-датасет.
    """
    item = await _load_item(db, item_id)
    current = item.current_assessment
    if current is None:
        raise HTTPException(status_code=404, detail="У материала нет оценки для правки")

    config = get_scoring_config()
    merged = {**current.scores, **payload.scores}
    flags = payload.escalation_flags if payload.escalation_flags is not None else current.escalation_flags

    try:
        computed = compute_score(merged, current.scheme, flags, config=config)
    except ScoringError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    for existing in item.assessments:
        existing.is_current = False

    updated = Assessment(
        item_id=item.id,
        profile_id=current.profile_id,
        scheme=computed.scheme,
        scores=computed.scores,
        rationales=current.rationales,
        index_value=computed.index_value,
        category=computed.category,
        escalation_flags=computed.escalation_flags,
        final_category=computed.final_category,
        author=Author.HUMAN,
        model=current.model,
        prompt_version=current.prompt_version,
        is_current=True,
    )
    db.add(updated)
    _log(db, "assessment", item.id, "scores", current.scores, computed.scores)
    item.is_relevant = computed.is_relevant

    await db.commit()
    await db.refresh(updated)
    return assessment_out(updated)


@router.post("/items/{item_id}/hide", status_code=status.HTTP_204_NO_CONTENT)
async def hide_item(
    item_id: int, payload: HideRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """Скрытие обратимо — FR-045. Причина сохраняется: без неё сигнал бесполезен
    для последующего тюнинга порогов."""
    if payload.hidden and not (payload.reason or "").strip():
        raise HTTPException(status_code=422, detail="Для скрытия материала укажите причину")
    item = await _load_item(db, item_id)
    _log(
        db,
        "item",
        item.id,
        "is_hidden",
        item.is_hidden,
        payload.hidden,
        (payload.reason or "").strip() or None,
    )
    item.is_hidden = payload.hidden
    await db.commit()
