"""Досье НПА и его хронология — FR-030…FR-037, ADR-0002.

НПА — не карточка новости, а долгоживущая сущность: стадии, версии, отзывы,
слушания и меняющаяся во времени оценка влияния. Смешение с новостью запрещено
принципом V конституции.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models._base import ActEventType, ActStage, Base, utcnow

if TYPE_CHECKING:
    from src.models.assessment import Assessment
    from src.models.item import Item


class Act(Base):
    __tablename__ = "acts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ключ связывания материалов с досье: «ФЗ № 243-ФЗ», «Законопроект № 1215252-8» (FR-036).
    act_identifier: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(256))
    stage: Mapped[ActStage] = mapped_column(String(32), index=True)
    source_url: Mapped[str] = mapped_column(String(1024))
    essence: Mapped[str] = mapped_column(Text)

    # Взят на отслеживание пользователем (FR-030).
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Архивирован после вступления в силу; хронология и история оценок сохраняются (FR-037).
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    timeline: Mapped[list[ActEvent]] = relationship(
        back_populates="act",
        cascade="all, delete-orphan",
        order_by="ActEvent.occurred_at",
        lazy="selectin",
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="act",
        cascade="all, delete-orphan",
        order_by="Assessment.created_at",
        foreign_keys="Assessment.act_id",
        lazy="selectin",
    )
    linked_items: Mapped[list[Item]] = relationship(
        back_populates="act", foreign_keys="Item.act_id"
    )

    @property
    def current_assessment(self) -> Assessment | None:
        return next((a for a in self.assessments if a.is_current), None)

    @property
    def previous_assessment(self) -> Assessment | None:
        """Для отображения «было / стало» при переоценке (находка исследования, раздел 6)."""
        history = [a for a in self.assessments if not a.is_current]
        return history[-1] if history else None

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Act {self.act_identifier!r} {self.stage}>"


class ActEvent(Base):
    """Событие хронологии досье — FR-033.

    Каждое событие ссылается на документ или на материал-основание: так diff, слушания
    и отзывы становятся узлами одной хронологии, а не разрозненными вкладками
    (паттерн EU Legislative Observatory).
    """

    __tablename__ = "act_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id", ondelete="CASCADE"), index=True)

    event_type: Mapped[ActEventType] = mapped_column(String(24))
    occurred_at: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(Text)

    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    # Подпись версии в формате «дата: стадия», а не голая дата: голые даты названы
    # худшим интерфейсом версий в обзоре (EUR-Lex, ~60 версий без подписей).
    version_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    document_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Дешёвая детекция изменения текста версии вместо полнотекстового diff (LegiScan).
    document_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    act: Mapped[Act] = relationship(back_populates="timeline")
