"""Оценка влияния — FR-015, FR-016, FR-017, FR-019.

Ключевой инвариант проекта (принцип II конституции, ADR-0003): в `scores` лежат
баллы 0-3, выставленные моделью, а `index_value`, `category` и `final_category`
вычислены кодом из этих баллов. Модель никогда не пишет сюда напрямую.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models._base import AssessmentScheme, Author, Base, utcnow

if TYPE_CHECKING:
    from src.models.act import Act
    from src.models.item import Item
    from src.models.profile import CompanyProfile


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ровно одно из двух заполнено: оценка новости либо оценка досье.
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    act_id: Mapped[int | None] = mapped_column(
        ForeignKey("acts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Под каким профилем оценивалось — FR-051. Смена профиля меняет оценку.
    profile_id: Mapped[int] = mapped_column(ForeignKey("company_profiles.id"), index=True)

    scheme: Mapped[AssessmentScheme] = mapped_column(String(16))
    # {"К1": 3, "К2": 2, ...} — целые 0-3, инвариант 3
    scores: Mapped[dict[str, int]] = mapped_column(JSON)
    # {"К1": "обоснование", ...} — по одному на каждый балл
    rationales: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)

    # Вычислено кодом по config/scoring.yaml — инвариант 2
    index_value: Mapped[float] = mapped_column(Float, index=True)
    category: Mapped[str] = mapped_column(String(32))
    escalation_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Категория после применения флагов: для НПА флаг делает её не ниже «Высокое» (FR-017)
    final_category: Mapped[str] = mapped_column(String(32), index=True)

    author: Mapped[Author] = mapped_column(String(8), default=Author.AI)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    item: Mapped[Item | None] = relationship(back_populates="assessments", foreign_keys=[item_id])
    act: Mapped[Act | None] = relationship(back_populates="assessments", foreign_keys=[act_id])
    profile: Mapped[CompanyProfile] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<Assessment {self.scheme} {self.index_value} {self.final_category}>"
