"""Сверка формулы индекса с реестром заказчика — задача T014.

Методика принадлежит заказчику. Если наша реализация расходится с числами в его
Excel хотя бы на одной карточке, все последующие измерения качества бессмысленны:
мы будем мерить не ту шкалу.
"""

from __future__ import annotations

from pathlib import Path

from src.evals.registry import load_dataset
from src.models import AssessmentScheme
from src.scoring import get_scoring_config
from src.scoring import score as compute_score

TOLERANCE = 0.05

SCHEME_BY_KIND = {
    "act": AssessmentScheme.NPA_K1_K6,
    "news": AssessmentScheme.NEWS_H1_H4,
}


def verify_against_registry(dataset_path: Path) -> dict:
    rows = load_dataset(dataset_path)
    config = get_scoring_config()

    checked = 0
    matched = 0
    mismatches: list[dict] = []
    category_mismatches: list[dict] = []

    for row in rows:
        expected = row.get("gold_index")
        if expected is None:
            continue

        scheme = SCHEME_BY_KIND[row["kind"]]
        # Флаг эскалации в реестре проставлен человеком; передаём его как факт,
        # а не пытаемся вывести — мы проверяем арифметику, а не распознавание флага.
        flags = (
            [config.escalation_flags[0].text]
            if row.get("gold_escalation") and config.escalation_flags
            else []
        )
        result = compute_score(row["gold_scores"], scheme, flags, config=config)

        checked += 1
        if abs(result.index_value - expected) <= TOLERANCE:
            matched += 1
        else:
            mismatches.append(
                {
                    "id": row["id"],
                    "computed": result.index_value,
                    "expected": expected,
                    "scores": row["gold_scores"],
                }
            )

        gold_final = (row.get("gold_final_category") or "").strip()
        if gold_final and result.final_category != gold_final:
            category_mismatches.append(
                {
                    "id": row["id"],
                    "computed": result.final_category,
                    "expected": gold_final,
                    "index": result.index_value,
                    "escalated": result.escalated,
                }
            )

    return {
        "checked": checked,
        "matched": matched,
        "mismatches": mismatches,
        "category_mismatches": category_mismatches,
    }
