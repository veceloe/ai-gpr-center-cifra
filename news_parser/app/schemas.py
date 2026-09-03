from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Period = Literal["day", "week", "month"]


class TopicOut(BaseModel):
    id: int
    period: Period
    slug: str
    title: str
    summary: str
    period_start: datetime
    period_end: datetime
    news_count: int = 0

    model_config = {"from_attributes": True}


class NewsOut(BaseModel):
    id: int
    channel_username: str
    channel_title: str | None
    text: str
    url: str | None
    published_at: datetime

    model_config = {"from_attributes": True}


class TopicsResponse(BaseModel):
    period: Period
    period_start: datetime
    period_end: datetime
    topics: list[TopicOut]


class TopicNewsResponse(BaseModel):
    topic: TopicOut
    news: list[NewsOut] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
