"""Схемы ответов модели — specs/001-ai-monitoring-center/contracts/llm-contracts.md.

Граница дозволенного: модель возвращает наблюдения (баллы, признаки, извлечённый
текст) и никогда — итоговую категорию, индекс или решение о публикации в ленте.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.models import Topic
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

    topic: Topic
    act_identifier: str | None = None

    @field_validator("act_identifier")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return v.strip() or None if isinstance(v, str) else v


# Латинские двойники кириллических букв, которыми названы критерии. Модель
# иногда возвращает «K1» с латинской K (U+004B) вместо кириллической К (U+041A)
# и «H1» с латинской H вместо Н: на вид JSON безупречен, а коды критериев не
# совпадают ни с одним из наших, и материал молча остаётся без оценки.
# Найдено при сравнении моделей: три карточки из 42 у deepseek-v4-flash.
HOMOGLYPHS = {"K": "К", "H": "Н"}


def normalize_criterion_code(code: str) -> str:
    """Привести код критерия к кириллице, если модель прислала латинский двойник."""
    return "".join(HOMOGLYPHS.get(ch, ch) for ch in code)


class ScoreResultRaw(BaseModel):
    """LLM-03 и LLM-04 · score_npa / score_news.

    Модель отдаёт баллы и обоснования; индекс и категорию считает код (ADR-0003).
    """

    scores: dict[str, int]
    rationales: dict[str, str] = Field(default_factory=dict)
    escalation_candidates: list[str] = Field(default_factory=list)

    @field_validator("rationales", mode="before")
    @classmethod
    def _rationale_codes(cls, v: dict) -> dict:
        if not isinstance(v, dict):
            return v
        return {normalize_criterion_code(str(code)): value for code, value in v.items()}

    @field_validator("scores", mode="before")
    @classmethod
    def _scores_in_range(cls, v: dict[str, int]) -> dict[str, int]:
        # Пустой набор баллов — никогда не валидный ответ, какой бы ни была схема.
        # Раньше он проходил контракт и отбраковывался позже, при подсчёте индекса,
        # так что повтор запроса не срабатывал и материал молча оставался без
        # оценки. Отклоняем здесь — и провайдер спрашивает модель ещё раз.
        if not isinstance(v, dict) or not v:
            raise ValueError("модель не вернула ни одного балла")
        clean: dict[str, int] = {}
        for raw_code, value in v.items():
            code = normalize_criterion_code(str(raw_code))
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{code}: балл должен быть целым, получено {value!r}")
            if not MIN_SCORE <= value <= MAX_SCORE:
                raise ValueError(f"{code}: балл {value} вне диапазона {MIN_SCORE}-{MAX_SCORE}")
            clean[code] = value
        return clean


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
