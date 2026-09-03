"""Базовый класс и перечисления модели данных.

Соответствует specs/001-ai-monitoring-center/data-model.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ItemType(StrEnum):
    """Две сущности продукта с разными жизненными циклами (ADR-0002)."""

    NEWS = "news"
    ACT = "act"


class Topic(StrEnum):
    """Тематическая категория из описания кейса. Не путать с категорией влияния."""

    REGULATORY = "regulatory"
    REPUTATION = "reputation"
    COMPETITORS = "competitors"
    TRENDS = "trends"


class Author(StrEnum):
    """Кто создал версию поля. Правка человека приоритетна и не затирается (принцип IV)."""

    AI = "ai"
    HUMAN = "human"


class AssessmentScheme(StrEnum):
    NPA_K1_K6 = "npa_k1_k6"
    NEWS_H1_H4 = "news_h1_h4"


class ActStage(StrEnum):
    """Стадии жизненного цикла НПА — FR-032.

    Порядок объявления совпадает с порядком прохождения и используется для сортировки.
    Расширение до четырёх состояний каждой стадии (завершена / идёт / неприменима /
    не достигнута) — открытое решение A7 на доске, в спецификации пока не закреплено.
    """

    ANNOUNCEMENT = "announcement"
    DRAFT_DISCUSSION = "draft_discussion"
    SUBMITTED = "submitted"
    READINGS = "readings"
    ADOPTED = "adopted"
    IN_FORCE = "in_force"


class ActEventType(StrEnum):
    """Тип события хронологии досье — FR-033."""

    STAGE_CHANGE = "stage_change"
    NEW_VERSION = "new_version"
    FEEDBACK = "feedback"
    HEARING = "hearing"
    OTHER = "other"
