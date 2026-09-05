"""Карточка события и разъединение кластера — FR-060, FR-062."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import StoryOut, story_out
from src.db import get_db
from src.models import Item, Story
from src.pipeline.dedup import split_story

router = APIRouter(tags=["items"])


async def _load_story(db: AsyncSession, story_id: int) -> Story:
    story = (
        await db.execute(
            select(Story)
            .where(Story.id == story_id)
            .options(selectinload(Story.items).selectinload(Item.source))
        )
    ).scalar_one_or_none()
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return story


@router.get("/stories/{story_id}", response_model=StoryOut)
async def get_story(story_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> StoryOut:
    """Карточка события: все источники и ссылки на оригиналы."""
    return story_out(await _load_story(db, story_id))


@router.post("/stories/{story_id}/split", status_code=status.HTTP_204_NO_CONTENT)
async def split_cluster(
    story_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    reason: str | None = None,
) -> None:
    """Разъединить ошибочно объединённый кластер — FR-062."""
    story = await _load_story(db, story_id)
    await split_story(db, story, reason=reason)
    await db.commit()
