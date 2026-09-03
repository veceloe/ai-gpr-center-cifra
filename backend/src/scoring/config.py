"""Загрузка методики оценки из config/scoring.yaml.

Методика принадлежит заказчику: веса, шкалы и пороги читаются из файла, а не
захардкожены. Изменение чисел требует ADR — см. конституцию, раздел «Рабочий процесс».
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from src.config import get_settings
from src.models import AssessmentScheme

MAX_SCORE = 3
MIN_SCORE = 0


class Criterion(BaseModel):
    code: str
    name: str
    weight: float
    scale: dict[int, str]

    @field_validator("scale")
    @classmethod
    def _scale_covers_range(cls, v: dict[int, str]) -> dict[int, str]:
        missing = set(range(MIN_SCORE, MAX_SCORE + 1)) - set(v)
        if missing:
            raise ValueError(f"шкала не покрывает баллы {sorted(missing)}")
        return v


class Category(BaseModel):
    min_score: float
    name: str
    reaction: str


class EscalationFlag(BaseModel):
    id: str
    text: str


class SchemeConfig(BaseModel):
    scheme: AssessmentScheme
    divisor: float
    criteria: list[Criterion]
    categories: list[Category]
    relevance_criterion: str

    @model_validator(mode="after")
    def _check(self) -> SchemeConfig:
        total = sum(c.weight for c in self.criteria)
        # Сумма весов в Excel заказчика — 1.0 с плавающей погрешностью, поэтому допуск.
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"сумма весов схемы {self.scheme} равна {total}, ожидалась 1.0")
        if self.relevance_criterion not in {c.code for c in self.criteria}:
            raise ValueError(f"критерий релевантности {self.relevance_criterion} отсутствует в схеме")
        if not self.categories:
            raise ValueError("не задана шкала категорий")
        return self

    @property
    def codes(self) -> list[str]:
        return [c.code for c in self.criteria]

    @property
    def ordered_categories(self) -> list[Category]:
        return sorted(self.categories, key=lambda c: c.min_score)

    def criterion(self, code: str) -> Criterion:
        for c in self.criteria:
            if c.code == code:
                return c
        raise KeyError(code)


class ScoringConfig(BaseModel):
    npa: SchemeConfig
    news: SchemeConfig
    escalation_flags: list[EscalationFlag] = Field(default_factory=list)

    def for_scheme(self, scheme: AssessmentScheme | str) -> SchemeConfig:
        # Сравнение через `==`, а не `is`: из базы значение приходит обычной строкой
        # (колонка String), и проверка на идентичность молча уводила оценку НПА
        # в схему новостей — критерии К1-К6 подменялись на Н1-Н4.
        return self.npa if scheme == AssessmentScheme.NPA_K1_K6 else self.news

    @property
    def allowed_flag_texts(self) -> set[str]:
        """Закрытый список: свободные формулировки от модели отбрасываются."""
        return {f.text for f in self.escalation_flags}

    def flag_id_by_text(self, text: str) -> str | None:
        return next((f.id for f in self.escalation_flags if f.text == text), None)


def load_scoring_config(path: Path | None = None) -> ScoringConfig:
    target = path or get_settings().scoring_config_path
    with Path(target).open(encoding="utf-8") as fh:
        return ScoringConfig.model_validate(yaml.safe_load(fh))


@lru_cache
def get_scoring_config() -> ScoringConfig:
    return load_scoring_config()
