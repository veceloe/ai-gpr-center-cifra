"""Минимальное досье НПА — T059, T060."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import ActCardOut, ActDetailOut, act_card, act_detail
from src.db import get_db
from src.models import Act, ActEvent, ActEventType, ActStage, Item, ItemType

router = APIRouter(tags=["acts"])


def _act_options():
    return (
        selectinload(Act.timeline),
        selectinload(Act.assessments),
        selectinload(Act.linked_items).selectinload(Item.source),
        selectinload(Act.linked_items).selectinload(Item.summaries),
        selectinload(Act.linked_items).selectinload(Item.assessments),
        selectinload(Act.linked_items).selectinload(Item.story),
    )


async def _load_act(db: AsyncSession, act_id: int) -> Act:
    act = (
        await db.execute(select(Act).where(Act.id == act_id).options(*_act_options()))
    ).scalar_one_or_none()
    if act is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Act not found")
    return act


async def _load_item(db: AsyncSession, item_id: int) -> Item:
    item = (
        await db.execute(
            select(Item)
            .where(Item.id == item_id)
            .options(
                selectinload(Item.source),
                selectinload(Item.summaries),
                selectinload(Item.assessments),
                selectinload(Item.story),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


def _new_act_from_item(item: Item) -> Act:
    summary = item.current_summary
    return Act(
        act_identifier=item.act_identifier or "",
        doc_type="НПА",
        stage=ActStage.ANNOUNCEMENT,
        source_url=item.url,
        essence=summary.text if summary and summary.text else item.title,
        is_tracked=True,
    )


def _initial_event(act: Act, item: Item) -> ActEvent:
    return ActEvent(
        act_id=act.id,
        event_type=ActEventType.OTHER,
        occurred_at=item.published_at.date(),
        description="Досье создано из материала.",
        source_item_id=item.id,
        document_url=item.url,
    )


@router.post(
    "/items/{item_id}/track-as-act",
    response_model=ActDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def track_as_act(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActDetailOut:
    item = await _load_item(db, item_id)
    if item.item_type != ItemType.ACT:
        raise HTTPException(status_code=422, detail="Материал не является НПА")

    if item.act_id is not None:
        act = await _load_act(db, item.act_id)
        act.is_tracked = True
    else:
        if not item.act_identifier:
            raise HTTPException(
                status_code=422,
                detail="Идентификатор НПА отсутствует: сначала нужна классификация",
            )
        act = (
            await db.execute(select(Act).where(Act.act_identifier == item.act_identifier))
        ).scalar_one_or_none()
        if act is None:
            act = _new_act_from_item(item)
            db.add(act)
            await db.flush()
            db.add(_initial_event(act, item))
        act.is_tracked = True
        item.act_id = act.id
        item.act = act

    await db.commit()
    return act_detail(await _load_act(db, act.id))


@router.get("/acts", response_model=list[ActCardOut])
async def list_acts(
    db: Annotated[AsyncSession, Depends(get_db)],
    stage: str | None = None,
    archived: Annotated[bool, Query()] = False,
) -> list[ActCardOut]:
    stmt = select(Act).where(Act.is_archived.is_(archived)).options(selectinload(Act.assessments))
    if stage:
        try:
            parsed_stage = ActStage(stage)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Неизвестная стадия: {stage}") from exc
        stmt = stmt.where(Act.stage == parsed_stage)
    acts = list((await db.execute(stmt.order_by(Act.updated_at.desc(), Act.id.desc()))).scalars())
    return [act_card(act) for act in acts]


@router.get("/acts/{act_id}", response_model=ActDetailOut)
async def get_act(
    act_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActDetailOut:
    return act_detail(await _load_act(db, act_id))
