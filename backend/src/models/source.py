"""Источник сбора — FR-002, FR-003, FR-004, FR-008."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models._base import Base, ItemType

if TYPE_CHECKING:
    from src.models.item import Item


class SourceType(StrEnum):
    RSS = "rss"
    WEB = "web"
    TELEGRAM = "telegram"
    MANUAL = "manual"


class SourceCategory(StrEnum):
    """Три категории источников из описания кейса — FR-001."""

    MEDIA = "media"
    REGULATOR = "regulator"
    TELEGRAM = "telegram"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[SourceType] = mapped_column(String(16), index=True)
    category: Mapped[SourceCategory] = mapped_column(String(16), index=True)
    # Тип определяется один раз при добавлении источника и копируется в Item.
    # LLM не должен менять схему оценки по содержимому отдельной публикации (FR-013).
    item_type: Mapped[ItemType] = mapped_column(String(16), default=ItemType.NEWS, index=True)
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    title: Mapped[str] = mapped_column(String(512))

    # Отключение без удаления: собранные материалы остаются (FR-004).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    poll_interval_min: Mapped[int] = mapped_column(Integer, default=15)

    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ошибка источника фиксируется, но не останавливает сбор из остальных (FR-008).
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Курсор инкрементального сбора: для Telegram — последний message_id.
    # Без него драфт перечитывал 200 последних сообщений каждый цикл (T097).
    last_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    items: Mapped[list[Item]] = relationship(back_populates="source")

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Source {self.type}:{self.title!r}>"
