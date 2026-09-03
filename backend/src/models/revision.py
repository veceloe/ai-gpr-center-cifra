"""Журнал правок — FR-042, FR-043, FR-081.

Две роли. Первая: защита правок пользователя от автоматической переобработки —
поле, у которого есть запись с author != ai, не перезаписывается (инвариант 6).
Вторая: расхождения машина/человек — эталонные метки для измерения точности.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models._base import Author, Base, utcnow


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 'item' | 'summary' | 'assessment'
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    field: Mapped[str] = mapped_column(String(64), index=True)

    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)

    author: Mapped[Author] = mapped_column(String(8), default=Author.HUMAN)
    # Причина правки — обязательна для «скрыть» и «разделить кластер»: клик без
    # причины бесполезен для тюнинга порогов (паттерн Feedly Leo).
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
