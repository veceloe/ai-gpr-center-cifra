"""Профиль компании — FR-050, FR-051, FR-052, ADR-0005.

Конфигурация релевантности, а не справочник организаций. Смена активного профиля
переоценивает ленту без изменений в коде — это и есть механизм переноса решения
на другую компанию группы.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models._base import Base


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    industry: Mapped[str] = mapped_column(Text)

    products: Mapped[list[str]] = mapped_column(JSON, default=list)
    regimes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Повышают К4, К5 и вероятность флага эскалации.
    risk_areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Повышают К3 при положительном знаке — льготы, гранты, сроки подачи.
    growth_areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    competitors: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Явные признаки шума для этого профиля.
    noise_markers: Mapped[list[str]] = mapped_column(JSON, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    def as_prompt_context(self) -> str:
        """Профиль в виде, пригодном для подстановки в промпт оценки.

        Формат человекочитаемый, а не JSON: модели проще опираться на связный текст,
        а нам — читать промпт в логе и понимать, что именно она видела.
        """
        blocks = [
            f"Компания: {self.name}",
            f"Деятельность: {self.industry.strip()}",
        ]
        for title, values in (
            ("Ключевые продукты", self.products),
            ("Регуляторные режимы и статусы", self.regimes),
            ("Зоны риска", self.risk_areas),
            ("Зоны роста", self.growth_areas),
            ("Конкуренты и смежные игроки", self.competitors),
            ("Явные признаки нерелевантности", self.noise_markers),
        ):
            if values:
                items = "\n".join(f"- {v}" for v in values)
                blocks.append(f"{title}:\n{items}")
        return "\n\n".join(blocks)

    def __repr__(self) -> str:  # pragma: no cover - диагностика
        return f"<CompanyProfile {self.slug}{' active' if self.is_active else ''}>"
