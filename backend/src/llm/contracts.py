"""Схемы ответов модели — specs/001-ai-monitoring-center/contracts/llm-contracts.md.

Граница дозволенного: модель возвращает наблюдения (баллы, признаки, извлечённый
текст) и никогда — итоговую категорию, индекс или решение о публикации в ленте.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.models import ItemType, Topic
from src.scoring.config import MAX_SCORE, MIN_SCORE


class Claim(BaseModel):
    """Утверждение саммари вместе с дословной цитатой-подтверждением."""

    statement: str = Field(description="Утверждение на русском языке, одно предложение")
    quote: str = Field(description="Дословный фрагмент исходного текста, подтверждающий утверждение")


class Entities(BaseModel):
    """Ключевые сущности — FR-011."""

    who: list[str] = Field(default_factory=list)
    what: str = ""
    when: str = ""
    consequences: str = ""


class SummarizeResult(BaseModel):
    """LLM-01 · summarize."""

    claims: list[Claim] = Field(default_factory=list)
    entities: Entities = Field(default_factory=Entities)


class ClassifyResult(BaseModel):
    """LLM-02 · classify."""

    item_type: ItemType
    topic: Topic
    act_identifier: str | None = None

    @field_validator("act_identifier")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return v.strip() or None if isinstance(v, str) else v


class ScoreResultRaw(BaseModel):
    """LLM-03 и LLM-04 · score_npa / score_news.

    Модель отдаёт баллы и обоснования; индекс и категорию считает код (ADR-0003).
    """

    scores: dict[str, int]
    rationales: dict[str, str] = Field(default_factory=dict)
    escalation_candidates: list[str] = Field(default_factory=list)

    @field_validator("scores")
    @classmethod
    def _scores_in_range(cls, v: dict[str, int]) -> dict[str, int]:
        for code, value in v.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{code}: балл должен быть целым, получено {value!r}")
            if not MIN_SCORE <= value <= MAX_SCORE:
                raise ValueError(f"{code}: балл {value} вне диапазона {MIN_SCORE}-{MAX_SCORE}")
        return v


class ClaimVerdict(BaseModel):
    index: int
    entailed: bool
    reason: str = ""


class VerifyClaimsResult(BaseModel):
    """LLM-06 · verify_claims — вторая ступень заземления (ADR-0007)."""

    verdicts: list[ClaimVerdict] = Field(default_factory=list)


class DedupPairResult(BaseModel):
    """LLM-05 · dedup_pair."""

    relation: str = Field(description="same_fact | different_positions | unrelated")
    reason: str = ""

    @field_validator("relation")
    @classmethod
    def _known_relation(cls, v: str) -> str:
        allowed = {"same_fact", "different_positions", "unrelated"}
        value = v.strip().lower()
        if value not in allowed:
            raise ValueError(f"relation должно быть одним из {sorted(allowed)}, получено {v!r}")
        return value
