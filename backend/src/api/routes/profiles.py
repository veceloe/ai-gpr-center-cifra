"""Профили компании — FR-050, FR-052, ADR-0005.

Переключение профиля переоценивает ленту без изменений в коде. Это и есть
демонстрируемая масштабируемость на другие компании группы.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ProfileOut
from src.db import get_db, get_session_factory
from src.models import CompanyProfile, Item

logger = logging.getLogger(__name__)
router = APIRouter(tags=["profiles"])


def _out(profile: CompanyProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        slug=profile.slug,
        name=profile.name,
        industry=profile.industry,
        products=profile.products or [],
        regimes=profile.regimes or [],
        risk_areas=profile.risk_areas or [],
        growth_areas=profile.growth_areas or [],
        competitors=profile.competitors or [],
        noise_markers=profile.noise_markers or [],
        is_active=profile.is_active,
    )


@router.get("/profiles", response_model=list[ProfileOut])
async def list_profiles(db: Annotated[AsyncSession, Depends(get_db)]) -> list[ProfileOut]:
    profiles = (await db.execute(select(CompanyProfile).order_by(CompanyProfile.id))).scalars().all()
    return [_out(p) for p in profiles]


async def _reassess_all() -> None:
    """Переоценка ленты под новый профиль.

    Сбрасывается только признак обработки: сами материалы, правки пользователя
    и история оценок остаются на месте.
    """
    from src.llm import build_provider
    from src.pipeline.runner import process_unprocessed

    async with get_session_factory()() as session:
        await session.execute(update(Item).values(processed_at=None))
        await session.commit()
        try:
            await process_unprocessed(session, build_provider(), limit=50)
        except Exception:
            logger.exception("Переоценка после смены профиля не завершилась")


@router.post("/profiles/{profile_id}/activate", status_code=status.HTTP_202_ACCEPTED)
async def activate_profile(
    profile_id: int,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    profile = await db.get(CompanyProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.execute(update(CompanyProfile).values(is_active=False))
    profile.is_active = True
    await db.commit()

    background.add_task(_reassess_all)
    return {"status": "accepted", "profile": profile.name}
