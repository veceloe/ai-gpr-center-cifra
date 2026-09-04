"""Вычисление индекса влияния — принцип II конституции, FR-016, FR-017, ADR-0003.

Здесь живёт вся арифметика оценки. Модель сюда не вмешивается: она поставляет
только баллы 0-3 и обоснования, а категорию и индекс определяет этот модуль.

Формула воспроизводит методику заказчика:

    ИВ = ( Σ (балл_i × вес_i) / divisor ) × 100,  округление до 0,1

Проверено на 42 фактических карточках реестра с исходной нумерацией до 46 —
tests/test_scoring_formula.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models import AssessmentScheme
from src.scoring.config import MAX_SCORE, MIN_SCORE, SchemeConfig, ScoringConfig, get_scoring_config

INDEX_PRECISION = 1


class ScoringError(ValueError):
    """Баллы не соответствуют схеме. Материал не теряется — попадает в ленту без оценки."""


@dataclass(frozen=True)
class ScoreResult:
    """Результат оценки. Всё, кроме scores и rationales, вычислено кодом."""

    scheme: AssessmentScheme
    scores: dict[str, int]
    index_value: float
    category: str
    escalation_flags: list[str]
    final_category: str
    is_relevant: bool
    reaction: str
    contributions: dict[str, float] = field(default_factory=dict)

    @property
    def escalated(self) -> bool:
        return self.category != self.final_category


def validate_scores(scores: dict[str, int], scheme: SchemeConfig) -> dict[str, int]:
    """Инвариант 3: каждый балл — целое от 0 до 3, присутствуют все критерии схемы."""
    expected = scheme.codes
    missing = [code for code in expected if code not in scores]
    if missing:
        raise ScoringError(f"отсутствуют баллы по критериям: {', '.join(missing)}")

    unknown = [code for code in scores if code not in expected]
    if unknown:
        raise ScoringError(f"неизвестные критерии: {', '.join(unknown)}")

    clean: dict[str, int] = {}
    for code in expected:
        raw = scores[code]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ScoringError(f"{code}: балл должен быть целым числом, получено {raw!r}")
        if not MIN_SCORE <= raw <= MAX_SCORE:
            raise ScoringError(f"{code}: балл {raw} вне диапазона {MIN_SCORE}-{MAX_SCORE}")
        clean[code] = raw
    return clean


def compute_index(scores: dict[str, int], scheme: SchemeConfig) -> tuple[float, dict[str, float]]:
    """Возвращает индекс 0-100 и вклад каждого критерия.

    Вклад нужен интерфейсу: пользователь должен видеть не только итог, но и то,
    какой критерий его сформировал.
    """
    contributions = {code: scores[code] * scheme.criterion(code).weight for code in scheme.codes}
    weighted = sum(contributions.values())
    index = round(weighted / scheme.divisor * 100, INDEX_PRECISION)
    return index, contributions


def resolve_category(index: float, scheme: SchemeConfig) -> tuple[str, str]:
    """Категория — наибольший порог, не превышающий индекс. Возвращает (имя, реакция)."""
    chosen = scheme.ordered_categories[0]
    for category in scheme.ordered_categories:
        if index >= category.min_score:
            chosen = category
        else:
            break
    return chosen.name, chosen.reaction


def apply_escalation(category: str, flags: list[str], scheme: SchemeConfig) -> tuple[str, str]:
    """Для НПА сработавший флаг делает итоговую категорию не ниже «Высокое» — FR-017.

    Excel-реестр заказчика применяет правило:
    если флаг стоит и базовая категория не «Критическое», итоговая категория — «Высокое».
    Для новостей флаги эскалации методикой не предусмотрены.
    """
    if not flags or scheme.scheme != AssessmentScheme.NPA_K1_K6:
        return resolve_category_by_name(category, scheme)

    target = "Критическое" if category == "Критическое" else "Высокое"
    return resolve_category_by_name(target, scheme)


def resolve_category_by_name(name: str, scheme: SchemeConfig) -> tuple[str, str]:
    for category in scheme.categories:
        if category.name == name:
            return category.name, category.reaction
    raise ScoringError(f"категория {name!r} отсутствует в шкале")


def normalize_flags(candidates: list[str] | None, config: ScoringConfig) -> list[str]:
    """Оставляет только формулировки из закрытого списка методики.

    Модель может предложить флаг лишь дословным текстом; всё остальное отбрасывается,
    иначе флаг эскалации перестаёт быть проверяемым правилом.
    """
    if not candidates:
        return []
    allowed = config.allowed_flag_texts
    return [text for text in dict.fromkeys(candidates) if text in allowed]


def score(
    scores: dict[str, int],
    scheme: AssessmentScheme,
    escalation_candidates: list[str] | None = None,
    config: ScoringConfig | None = None,
) -> ScoreResult:
    """Полная оценка: валидация баллов, индекс, категория, флаги, релевантность."""
    cfg = config or get_scoring_config()
    scheme_cfg = cfg.for_scheme(scheme)

    clean = validate_scores(scores, scheme_cfg)
    index, contributions = compute_index(clean, scheme_cfg)
    category, reaction = resolve_category(index, scheme_cfg)

    flags = (
        normalize_flags(escalation_candidates, cfg)
        if scheme_cfg.scheme == AssessmentScheme.NPA_K1_K6
        else []
    )
    final_category, final_reaction = apply_escalation(category, flags, scheme_cfg)

    # Релевантность выводится из критерия применимости, а не запрашивается отдельно:
    # К1 (или Н2) отвечает ровно на этот вопрос — экономия вызова и никаких
    # противоречий между двумя ответами модели об одном и том же.
    is_relevant = clean[scheme_cfg.relevance_criterion] > 0

    return ScoreResult(
        scheme=scheme,
        scores=clean,
        index_value=index,
        category=category,
        escalation_flags=flags,
        final_category=final_category,
        is_relevant=is_relevant,
        reaction=final_reaction if flags else reaction,
        contributions=contributions,
    )
