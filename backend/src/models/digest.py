"""Дайджест под получателя — FR-070, FR-071, FR-072.

По данным исследования это не бонус, а механизм удержания: новостные агрегаторы
умирают на реактивном использовании, а обязательный рабочий артефакт для руководства
встроен в дедлайн специалиста.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models._base import Base, utcnow

if TYPE_CHECKING:
    from src.models.item import Item


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entries: Mapped[list[DigestItem]] = relationship(
        back_populates="digest",
        cascade="all, delete-orphan",
        order_by="DigestItem.position",
    )


class DigestItem(Base):
    __tablename__ = "digest_items"
    __table_args__ = (UniqueConstraint("digest_id", "item_id", name="uq_digest_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digests.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Исключение из дайджеста не удаляет материал из ленты (FR-071).
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    digest: Mapped[Digest] = relationship(back_populates="entries")
    item: Mapped[Item] = relationship()
