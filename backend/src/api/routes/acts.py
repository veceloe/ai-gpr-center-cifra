"""Минимальное досье НПА — T059, T060."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ActCardOut,
    ActDetailOut,
    ActEventCreate,
    ActPatch,
    LinkItemRequest,
    act_card,
    act_detail,
)
from src.db import get_db
from src.models import Act, ActEvent, ActEventType, ActStage, Author, Item, ItemType, Revision
from src.pipeline.act_identifier import canonical_act_identifier

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
        await db.execute(
            select(Act)
            .where(Act.id == act_id)
            # populate_existing обязателен: без него объект берётся из карты
            # идентичности сессии вместе с устаревшими коллекциями, и только что
            # добавленное событие хронологии в ответ не попадает.
            .execution_options(populate_existing=True)
            .options(*_act_options())
        )
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
        identifier = canonical_act_identifier(item.act_identifier, item.url)
        item.act_identifier = identifier
        if not identifier:
            raise HTTPException(
                status_code=422,
                detail="Идентификатор НПА отсутствует: сначала нужна классификация",
            )
        act = (await db.execute(select(Act).where(Act.act_identifier == identifier))).scalar_one_or_none()
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


STAGE_LABELS = {
    ActStage.ANNOUNCEMENT: "анонс",
    ActStage.DRAFT_DISCUSSION: "проект на обсуждении",
    ActStage.SUBMITTED: "внесён",
    ActStage.READINGS: "рассмотрение в чтениях",
    ActStage.ADOPTED: "принят",
    ActStage.IN_FORCE: "вступил в силу",
}


@router.patch("/acts/{act_id}", response_model=ActDetailOut)
async def patch_act(
    act_id: int,
    payload: ActPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActDetailOut:
    """Смена стадии и архивация — FR-032, FR-037.

    Смена стадии порождает событие хронологии и помечает досье к переоценке
    (FR-034): документ, который раньше затрагивал компанию, после новой стадии
    может затрагивать её иначе.
    """
    act = await _load_act(db, act_id)
    data = payload.model_dump(exclude_unset=True)

    if "stage" in data and data["stage"] is not None:
        try:
            new_stage = ActStage(data["stage"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Неизвестная стадия: {data['stage']}") from exc

        if new_stage != act.stage:
            was = STAGE_LABELS.get(ActStage(act.stage), str(act.stage))
            became = STAGE_LABELS.get(new_stage, str(new_stage))
            db.add(
                ActEvent(
                    act_id=act.id,
                    event_type=ActEventType.STAGE_CHANGE,
                    occurred_at=date.today(),
                    description=f"Стадия изменена: {was} → {became}.",
                )
            )
            db.add(
                Revision(
                    entity_type="act",
                    entity_id=act.id,
                    field="stage",
                    old_value=str(act.stage),
                    new_value=str(new_stage),
                    author=Author.HUMAN,
                )
            )
            act.stage = new_stage
            # Переоценка при смене стадии: сбрасываем признак обработки у связанных
            # материалов, чтобы конвейер пересчитал влияние с новой юридической силой.
            for linked in act.linked_items:
                linked.processed_at = None

    for field in ("is_archived", "is_tracked", "effective_from", "essence", "doc_type"):
        if field in data and data[field] is not None:
            setattr(act, field, data[field])

    await db.commit()
    return act_detail(await _load_act(db, act_id))


@router.post(
    "/acts/{act_id}/events",
    response_model=ActDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_act_event(
    act_id: int,
    payload: ActEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActDetailOut:
    """Добавить событие в хронологию — FR-033.

    Каждое событие ссылается на документ или материал-основание: так версии,
    отзывы и слушания становятся узлами одной хронологии, а не отдельными вкладками.
    """
    act = await _load_act(db, act_id)
    try:
        event_type = ActEventType(payload.event_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Неизвестный тип события: {payload.event_type}"
        ) from exc

    db.add(
        ActEvent(
            act_id=act.id,
            event_type=event_type,
            occurred_at=payload.occurred_at,
            description=payload.description.strip(),
            version_label=payload.version_label,
            document_url=payload.document_url,
            source_item_id=payload.source_item_id,
        )
    )
    await db.commit()
    return act_detail(await _load_act(db, act_id))


@router.post("/acts/{act_id}/link-item", response_model=ActDetailOut)
async def link_item(
    act_id: int,
    payload: LinkItemRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActDetailOut:
    """Связать поступивший материал с существующим досье — FR-036."""
    act = await _load_act(db, act_id)
    item = await _load_item(db, payload.item_id)

    if item.act_id == act.id:
        return act_detail(act)

    item.act_id = act.id
    db.add(
        ActEvent(
            act_id=act.id,
            event_type=ActEventType.OTHER,
            occurred_at=item.published_at.date(),
            description=f"К досье привязан материал: {item.title[:180]}",
            source_item_id=item.id,
            document_url=item.url,
        )
    )
    await db.commit()
    return act_detail(await _load_act(db, act_id))
