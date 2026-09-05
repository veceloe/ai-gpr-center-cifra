"""Материал, саммари и кластер события."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models._base import Author, Base, ItemType, Topic, utcnow

if TYPE_CHECKING:
    from src.models.act import Act
    from src.models.assessment import Assessment
    from src.models.source import Source


class Story(Base):
    """Кластер публикаций об одном факте — FR-060.

    В одну карточку попадают только материалы про один и тот же факт.
    Различающиеся позиции (`different_positions`) не склеиваются: это ценность, а не шум (FR-061, H-05).
    """

    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_title: Mapped[str] = mapped_column(String(512))
    fact_summary: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    was_split_by_user: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list[Item]] = relationship(back_populates="story")


class Item(Base):
    """Собранная единица контента — FR-006, FR-007."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)

    # Ключ дедупликации по URL (FR-007).
    url: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(1024))
    raw_text: Mapped[str] = mapped_column(Text)
    # Обнаружение изменения текста по тому же URL.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Дата не найдена в источнике — использована дата сбора; признак виден пользователю.
    published_at_is_approx: Mapped[bool] = mapped_column(Boolean, default=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Для замера времени обработки — FR-080, SC-003.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item_type: Mapped[ItemType] = mapped_column(String(16), default=ItemType.NEWS, index=True)
    topic: Mapped[Topic | None] = mapped_column(String(16), nullable=True, index=True)

    # Текст закрыт подпиской — обработан анонс (граничный случай из spec.md).
    is_partial_text: Mapped[bool] = mapped_column(Boolean, default=False)
    # Результат оценки релевантности профилю (FR-018). None — ещё не оценено.
    is_relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    # Скрыт пользователем, обратимо (FR-045).
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Оценка не получена после повторов — материал в ленте с пометкой, но не потерян.
    assessment_failed: Mapped[bool] = mapped_column(Boolean, default=False)

    story_id: Mapped[int | None] = mapped_column(ForeignKey("stories.id"), nullable=True, index=True)
    act_id: Mapped[int | None] = mapped_column(ForeignKey("acts.id"), nullable=True, index=True)
    act_identifier: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)

    # Рабочая пометка пользователя, доступна в поиске (FR-044).
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    # lazy="selectin" здесь не оптимизация, а корректность: пайплайн работает
    # в асинхронном контексте, где ленивая подгрузка падает с MissingGreenlet.
    # Эти три связи нужны при любой работе с материалом, поэтому грузим сразу.
    source: Mapped[Source] = relationship(back_populates="items", lazy="selectin")
    story: Mapped[Story | None] = relationship(back_populates="items")
    act: Mapped[Act | None] = relationship(back_populates="linked_items", foreign_keys=[act_id])
    summaries: Mapped[list[Summary]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="Summary.created_at",
        lazy="selectin",
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="Assessment.created_at",
        foreign_keys="Assessment.item_id",
        lazy="selectin",
    )

    @property
    def current_summary(self) -> Summary | None:
        """Инвариант 1: ровно одна версия с is_current."""
        return next((s for s in self.summaries if s.is_current), None)

    @property
    def current_assessment(self) -> Assessment | None:
        return next((a for a in self.assessments if a.is_current), None)

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Item {self.id} {self.title[:40]!r}>"


class Summary(Base):
    """Саммари с заземлением на оригинал — FR-010, FR-012, FR-090, FR-092.

    Хранит ВСЕ утверждения, включая отбракованные: доля отбраковки по причинам должна
    быть измеримой (FR-092), а пользователь — видеть счётчик неподтверждённого.
    В текст саммари попадают только прошедшие обе ступени.
    """

    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)

    text: Mapped[str] = mapped_column(Text)
    # [{statement, quote, char_start, char_end, quote_found, entailed, reject_reason}]
    claims: Mapped[list[dict]] = mapped_column(JSON, default=list)
    # {who: [...], what: str, when: str, consequences: str}
    entities: Mapped[dict] = mapped_column(JSON, default=dict)

    author: Mapped[Author] = mapped_column(String(8), default=Author.AI)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    item: Mapped[Item] = relationship(back_populates="summaries")

    @property
    def accepted_claims(self) -> list[dict]:
        return [c for c in self.claims if c.get("quote_found") and c.get("entailed")]

    @property
    def rejected_claims(self) -> list[dict]:
        """Счётчик «N утверждений не подтверждены» — молчаливое отбрасывание
        рождает страх пропуска и параллельный Excel."""
        return [c for c in self.claims if not (c.get("quote_found") and c.get("entailed"))]
