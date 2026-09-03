from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Period
from app.database import get_db
from app.models import Post, Topic, TopicPost
from app.periods import period_bounds
from app.schemas import (
    HealthResponse,
    NewsOut,
    TopicNewsResponse,
    TopicOut,
    TopicsResponse,
)

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/topics", response_model=TopicsResponse)
async def list_topics(
    period: Annotated[Period, Query(description="day | week | month")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TopicsResponse:
    period_start, period_end = period_bounds(period)

    count_subq = (
        select(TopicPost.topic_id, func.count(TopicPost.id).label("news_count")).group_by(TopicPost.topic_id).subquery()
    )

    query = (
        select(Topic, func.coalesce(count_subq.c.news_count, 0))
        .outerjoin(count_subq, Topic.id == count_subq.c.topic_id)
        .where(Topic.period == period)
        .order_by(func.coalesce(count_subq.c.news_count, 0).desc(), Topic.title)
    )
    result = await db.execute(query)
    rows = result.all()

    topics = [
        TopicOut(
            id=topic.id,
            period=topic.period,
            slug=topic.slug,
            title=topic.title,
            summary=topic.summary,
            period_start=topic.period_start,
            period_end=topic.period_end,
            news_count=int(news_count),
        )
        for topic, news_count in rows
    ]

    return TopicsResponse(
        period=period,
        period_start=period_start,
        period_end=period_end,
        topics=topics,
    )


@router.get("/topics/{topic_id}/news", response_model=TopicNewsResponse)
async def topic_news(
    topic_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TopicNewsResponse:
    query = (
        select(Topic).where(Topic.id == topic_id).options(selectinload(Topic.post_links).selectinload(TopicPost.post))
    )
    result = await db.execute(query)
    topic = result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    news_count = len(topic.post_links)
    topic_out = TopicOut(
        id=topic.id,
        period=topic.period,
        slug=topic.slug,
        title=topic.title,
        summary=topic.summary,
        period_start=topic.period_start,
        period_end=topic.period_end,
        news_count=news_count,
    )

    posts: list[Post] = sorted(
        (link.post for link in topic.post_links if link.post),
        key=lambda p: p.published_at,
        reverse=True,
    )

    return TopicNewsResponse(
        topic=topic_out,
        news=[NewsOut.model_validate(p) for p in posts],
    )
