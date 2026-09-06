"""Измерение качества оценки на эталоне заказчика — задача T083, SC-005…SC-013.

ПОЧЕМУ ЗДЕСЬ НЕТ ОДИНОЧНОЙ ЦИФРЫ ТОЧНОСТИ. Большинство материалов в потоке
нерелевантны, поэтому классификатор «всё нерелевантно» набирает высокую accuracy
и остаётся бесполезным. Ровно на этой ошибке FiscalNote годами продавала
предсказание «с точностью более 94%» при доле принимаемых актов в единицы
процентов, не публикуя ни базовую ставку, ни precision, ни recall.

Поэтому отчёт всегда печатает базовую ставку и baseline большинства рядом
с результатом. Ведущая метрика — recall по классу «релевантно»: цена пропуска
релевантного материала для GR несопоставимо выше цены лишнего в ленте.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from src.evals.registry import load_dataset
from src.llm.contracts import ScoreResultRaw
from src.llm.prompts import build_score_prompt, score_user_message
from src.llm.provider import LLMError, LLMProvider
from src.models import AssessmentScheme
from src.scoring import ScoringError, get_scoring_config
from src.scoring import score as compute_score

logger = logging.getLogger(__name__)

SCHEME_BY_KIND = {"act": AssessmentScheme.NPA_K1_K6, "news": AssessmentScheme.NEWS_H1_H4}

# Категории, провал которых в нижние — недопустим (SC-006).
CRITICAL_CATEGORIES = {"Высокое", "Критическое", "Горячая тема"}
BOTTOM_CATEGORIES = {"Низкое", "Незначительное", "Фон", "На заметку"}

MAX_CONCURRENT = 4


DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def card_date(row: dict) -> date | None:
    """Дата карточки эталона, если реестр её содержит.

    В реестре заказчика колонка со стадией у новостей хранит дату
    («06.08.2026», «05–06.08.2026 (данные II кв.)»), а у актов — стадию
    прохождения. Берём последнюю дату в строке: диапазон «05–06.08» означает,
    что событие завершилось шестого.
    """
    matches = DATE_RE.findall(str(row.get("stage") or ""))
    if not matches:
        return None
    day, month, year = matches[-1]
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def build_user_message(row: dict) -> str:
    """Собрать вход модели из полей эталонной карточки.

    Тип документа и стадия лежат в реестре отдельными колонками, а в живом
    потоке приходят внутри текста материала. Если их не подставить, критерий
    К2 «юридическая сила» оценивается вслепую.

    Даты публикации реестр не хранит — так и пишем. В первой версии в это поле
    подставлялась стадия акта, и модель читала «Дата публикации: Законопроект
    внесён, I чтение».
    """
    text = row.get("text") or row["identifier"]
    known = card_date(row)
    context = row.get("doc_type") or ""
    stage = row.get("stage") or ""
    # У актов в этой колонке стадия — она нужна модели. У новостей там дата,
    # и она уходит в отдельное поле, а не в заголовок.
    if stage and known is None:
        context = f"{context} · {stage}".strip(" ·")
    title = f"{row['identifier']} — {context}" if context else row["identifier"]
    return score_user_message(title, text, text, known.strftime("%d.%m.%Y") if known else "не указана")


@dataclass
class CardResult:
    card_id: int
    kind: str
    identifier: str
    gold_scores: dict[str, int]
    gold_relevant: bool
    gold_category: str
    predicted_scores: dict[str, int] | None = None
    predicted_index: float | None = None
    predicted_category: str | None = None
    predicted_relevant: bool | None = None
    predicted_rationales: dict[str, str] = field(default_factory=dict)
    error: str | None = None


@dataclass
class Report:
    results: list[CardResult] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def scored(self) -> list[CardResult]:
        return [r for r in self.results if r.predicted_relevant is not None]

    @property
    def failed(self) -> list[CardResult]:
        return [r for r in self.results if r.error]

    # --- база для честного чтения любой доли -------------------------------
    @property
    def base_rate(self) -> float:
        """Доля релевантных в эталоне. Без неё accuracy не значит ничего."""
        if not self.scored:
            return 0.0
        return sum(r.gold_relevant for r in self.scored) / len(self.scored)

    @property
    def majority_baseline(self) -> float:
        """Accuracy тривиального классификатора: всегда отвечать классом-большинством."""
        rate = self.base_rate
        return max(rate, 1 - rate)

    @property
    def accuracy(self) -> float:
        if not self.scored:
            return 0.0
        hits = sum(r.predicted_relevant == r.gold_relevant for r in self.scored)
        return hits / len(self.scored)

    @property
    def precision(self) -> float:
        predicted_positive = [r for r in self.scored if r.predicted_relevant]
        if not predicted_positive:
            return 0.0
        return sum(r.gold_relevant for r in predicted_positive) / len(predicted_positive)

    @property
    def recall(self) -> float:
        actual_positive = [r for r in self.scored if r.gold_relevant]
        if not actual_positive:
            return 0.0
        return sum(bool(r.predicted_relevant) for r in actual_positive) / len(actual_positive)

    @property
    def critical_drops(self) -> list[CardResult]:
        """Материал, который эксперт отнёс к верхним категориям, а система — к нижним.

        Ключевое условие заказчика. Целевое значение — ноль, и оно важнее
        общей точности: пропущенное регуляторное изменение стоит дороже
        десятка лишних материалов в ленте.
        """
        return [
            r
            for r in self.scored
            if r.gold_category in CRITICAL_CATEGORIES and r.predicted_category in BOTTOM_CATEGORIES
        ]

    def mae_by_criterion(self) -> dict[str, float]:
        """Средняя абсолютная ошибка по каждому критерию отдельно.

        Показывает, какой именно критерий чинить, вместо одной размытой цифры.
        """
        sums: dict[str, list[int]] = {}
        for r in self.scored:
            if r.predicted_scores is None:
                continue
            for code, gold in r.gold_scores.items():
                predicted = r.predicted_scores.get(code)
                if predicted is None:
                    continue
                sums.setdefault(code, []).append(abs(predicted - gold))
        return {code: sum(v) / len(v) for code, v in sorted(sums.items()) if v}

    def category_distance(self) -> dict[str, int]:
        """Расхождение категории: совпало, на ступень, больше чем на ступень."""
        config = get_scoring_config()
        out = {"точно": 0, "на ступень": 0, "больше ступени": 0}
        for r in self.scored:
            scheme = config.for_scheme(SCHEME_BY_KIND[r.kind])
            names = [c.name for c in scheme.ordered_categories]
            if r.gold_category not in names or r.predicted_category not in names:
                continue
            distance = abs(names.index(r.predicted_category) - names.index(r.gold_category))
            key = "точно" if distance == 0 else "на ступень" if distance == 1 else "больше ступени"
            out[key] += 1
        return out


async def evaluate(
    dataset_path: Path,
    provider: LLMProvider,
    profile_context: str,
    limit: int | None = None,
) -> Report:
    rows = load_dataset(dataset_path)
    if limit:
        rows = rows[:limit]

    config = get_scoring_config()
    today = datetime.now(UTC).date()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    started = datetime.now(UTC)

    async def one(row: dict) -> CardResult:
        scheme = SCHEME_BY_KIND[row["kind"]]
        scheme_cfg = config.for_scheme(scheme)
        gold_relevant = row["gold_scores"][scheme_cfg.relevance_criterion] > 0

        result = CardResult(
            card_id=row["id"],
            kind=row["kind"],
            identifier=row["identifier"],
            gold_scores=row["gold_scores"],
            gold_relevant=gold_relevant,
            gold_category=row.get("gold_final_category") or row.get("gold_category") or "",
        )

        # Оцениваем от даты самой карточки, а не от сегодняшнего дня. Критерий
        # Н1 «Актуальность» измеряется относительно «сейчас» («произошло на этой
        # неделе» — 3 балла), и эксперт заказчика проставлял баллы в момент
        # публикации. Сравнивать его августовскую тройку с оценкой на сентябрь
        # значит измерять календарь, а не качество модели.
        prompt = build_score_prompt(scheme, config, profile_context, card_date(row) or today)

        async with semaphore:
            try:
                raw = await provider.complete_json(
                    prompt.id,
                    prompt.system,
                    build_user_message(row),
                    ScoreResultRaw,
                )
            except LLMError as exc:
                result.error = f"модель: {str(exc)[:160]}"
                return result

        try:
            computed = compute_score(raw.scores, scheme, raw.escalation_candidates, config=config)
        except ScoringError as exc:
            result.error = f"баллы: {exc}"
            return result

        result.predicted_rationales = raw.rationales
        result.predicted_scores = computed.scores
        result.predicted_index = computed.index_value
        result.predicted_category = computed.final_category
        result.predicted_relevant = computed.is_relevant
        return result

    results = await asyncio.gather(*(one(row) for row in rows))
    report = Report(results=list(results))
    report.duration_seconds = (datetime.now(UTC) - started).total_seconds()
    return report


def format_report(report: Report) -> str:
    """Текстовый отчёт. Базовая ставка печатается рядом с любой долей — всегда."""
    lines: list[str] = []
    n = len(report.scored)
    lines.append(f"Карточек оценено: {n} из {len(report.results)}")
    if report.failed:
        lines.append(f"Не удалось оценить: {len(report.failed)}")
        for r in report.failed[:5]:
            lines.append(f"  #{r.card_id} {r.identifier[:50]} — {r.error}")
    if n == 0:
        return "\n".join(lines)

    lines.append("")
    lines.append("--- База для чтения долей ---")
    lines.append(f"Базовая ставка (доля релевантных в эталоне): {report.base_rate:.1%}")
    lines.append(f"Baseline большинства (accuracy тривиального классификатора): {report.majority_baseline:.1%}")

    lines.append("")
    lines.append("--- Релевантность ---")
    lines.append(f"Recall  (SC-005, цель ≥ 0,80): {report.recall:.1%}")
    lines.append(f"Precision (SC-005, цель ≥ 0,70): {report.precision:.1%}")
    lines.append(f"Accuracy: {report.accuracy:.1%} — читать только вместе с базовой ставкой выше")
    beats = report.accuracy > report.majority_baseline
    lines.append(
        f"Превосходит baseline большинства (SC-013): {'да' if beats else 'НЕТ — результат отрицательный'}"
    )

    lines.append("")
    lines.append("--- Провалы критичного (SC-006, цель 0) ---")
    drops = report.critical_drops
    lines.append(f"Материалов «Высокое/Критическое», ушедших в нижние категории: {len(drops)}")
    for r in drops:
        lines.append(f"  #{r.card_id} {r.identifier[:56]}: {r.gold_category} → {r.predicted_category}")

    lines.append("")
    lines.append("--- Расхождение категории ---")
    for key, value in report.category_distance().items():
        lines.append(f"  {key}: {value}")

    lines.append("")
    lines.append("--- MAE по критериям (какой чинить) ---")
    for code, mae in sorted(report.mae_by_criterion().items(), key=lambda kv: -kv[1]):
        lines.append(f"  {code}: {mae:.2f}")

    lines.append("")
    lines.append(f"Время прогона: {report.duration_seconds:.0f} с")
    return "\n".join(lines)


def dump_cards(report: Report) -> str:
    """Построчный разбор: по одной карточке в строке JSON.

    Без него отчёт даёт только сводные числа, и непонятно, почему именно
    расходится оценка. Здесь рядом лежат эталонные баллы, машинные баллы и
    обоснование модели — расхождение можно прочитать, а не додумать.
    """
    import json

    lines = []
    for r in report.results:
        lines.append(
            json.dumps(
                {
                    "id": r.card_id,
                    "kind": r.kind,
                    "identifier": r.identifier,
                    "gold_scores": r.gold_scores,
                    "predicted_scores": r.predicted_scores,
                    "gold_category": r.gold_category,
                    "predicted_category": r.predicted_category,
                    "delta": (
                        {k: r.predicted_scores.get(k, 0) - v for k, v in r.gold_scores.items()}
                        if r.predicted_scores
                        else None
                    ),
                    "rationales": r.predicted_rationales,
                    "error": r.error,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)
