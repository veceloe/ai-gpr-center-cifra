"""Формула индекса влияния — задача T014, принцип II конституции.

Главный тест проекта: если формула расходится с реестром заказчика, вся оценка
измеряет не ту шкалу.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app
from src.evals.formula_check import verify_against_registry
from src.models import AssessmentScheme
from src.scoring import ScoringError, get_scoring_config, score

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET = REPO_ROOT / "evals" / "registry_46.jsonl"


class TestFormulaAgainstCustomerRegistry:
    """Сверка с числами, которые заказчик посчитал сам в Excel."""

    @pytest.mark.skipif(not DATASET.exists(), reason="эталон не собран: python -m src.cli parse-registry")
    def test_index_matches_registry_exactly(self) -> None:
        report = verify_against_registry(DATASET)
        assert report["checked"] > 0, "в эталоне нет карточек с проставленным индексом"
        assert report["mismatches"] == [], (
            f"формула разошлась с реестром на {len(report['mismatches'])} карточках: "
            f"{report['mismatches'][:3]}"
        )

    @pytest.mark.skipif(not DATASET.exists(), reason="эталон не собран")
    def test_final_category_matches_registry(self) -> None:
        """Категория после применения флага эскалации — FR-017."""
        report = verify_against_registry(DATASET)
        assert report["category_mismatches"] == [], (
            f"итоговая категория разошлась на {len(report['category_mismatches'])} карточках: "
            f"{report['category_mismatches'][:3]}"
        )


class TestKnownCards:
    """Карточки реестра, посчитанные вручную — на случай, если датасет не собран."""

    def test_cas_drm_card(self) -> None:
        # Карточка № 1: CAS DRM. В Excel — индекс 65,0, категория «Среднее»,
        # флаг эскалации «Да», итоговая категория «Высокое».
        result = score(
            {"К1": 3, "К2": 2, "К3": 3, "К4": 0, "К5": 0, "К6": 3},
            AssessmentScheme.NPA_K1_K6,
        )
        assert result.index_value == 65.0
        assert result.category == "Среднее"
        assert result.is_relevant is True

    def test_ai_law_card(self) -> None:
        # Карточка № 2: ФЗ № 243-ФЗ. В Excel — 51,7, «Среднее».
        result = score(
            {"К1": 3, "К2": 3, "К3": 1, "К4": 1, "К5": 0, "К6": 0},
            AssessmentScheme.NPA_K1_K6,
        )
        assert result.index_value == 51.7
        assert result.category == "Среднее"

    def test_kii_decree_card(self) -> None:
        # Карточка № 22: ПП № 402. В Excel — 78,3, «Высокое».
        result = score(
            {"К1": 3, "К2": 3, "К3": 2, "К4": 2, "К5": 1, "К6": 3},
            AssessmentScheme.NPA_K1_K6,
        )
        assert result.index_value == 78.3
        assert result.category == "Высокое"

    def test_news_datacenter_card(self) -> None:
        # Карточка № 3 листа новостей: кризис ЦОД. В Excel — 83,3, «Горячая тема».
        result = score({"Н1": 3, "Н2": 2, "Н3": 3, "Н4": 2}, AssessmentScheme.NEWS_H1_H4)
        assert result.index_value == 83.3
        assert result.category == "Горячая тема"


class TestEscalation:
    @pytest.mark.parametrize(
        "scores,base_category,final_category",
        [
            ({"К1": 0, "К2": 0, "К3": 0, "К4": 0, "К5": 0, "К6": 0}, "Незначительное", "Высокое"),
            ({"К1": 0, "К2": 0, "К3": 0, "К4": 0, "К5": 3, "К6": 3}, "Низкое", "Высокое"),
            ({"К1": 3, "К2": 2, "К3": 3, "К4": 0, "К5": 0, "К6": 3}, "Среднее", "Высокое"),
            ({"К1": 0, "К2": 3, "К3": 3, "К4": 3, "К5": 3, "К6": 3}, "Высокое", "Высокое"),
            ({"К1": 3, "К2": 3, "К3": 3, "К4": 3, "К5": 3, "К6": 3}, "Критическое", "Критическое"),
        ],
    )
    def test_npa_flag_sets_final_category_to_high_unless_already_critical(
        self, scores: dict[str, int], base_category: str, final_category: str
    ) -> None:
        """Excel-реестр: флаг НПА делает итоговую категорию не ниже «Высокое»."""
        flag = get_scoring_config().escalation_flags[0].text
        result = score(scores, AssessmentScheme.NPA_K1_K6, escalation_candidates=[flag])

        assert result.category == base_category
        assert result.final_category == final_category
        assert result.escalated == (base_category != final_category)

    def test_unknown_flag_text_is_discarded(self) -> None:
        """Свободная формулировка от модели не считается флагом.

        Иначе флаг эскалации перестаёт быть проверяемым правилом методики.
        """
        result = score(
            {"К1": 3, "К2": 2, "К3": 3, "К4": 0, "К5": 0, "К6": 3},
            AssessmentScheme.NPA_K1_K6,
            escalation_candidates=["Мне кажется, это важно"],
        )
        assert result.escalation_flags == []
        assert result.final_category == "Среднее"

    def test_top_category_does_not_overflow(self) -> None:
        flag = get_scoring_config().escalation_flags[0].text
        result = score(
            {"К1": 3, "К2": 3, "К3": 3, "К4": 3, "К5": 3, "К6": 3},
            AssessmentScheme.NPA_K1_K6,
            escalation_candidates=[flag],
        )
        assert result.index_value == 100.0
        assert result.final_category == "Критическое"

    def test_news_ignores_escalation_candidates(self) -> None:
        """Для news методика флагов эскалации не задаёт."""
        flag = get_scoring_config().escalation_flags[0].text
        result = score(
            {"Н1": 0, "Н2": 1, "Н3": 0, "Н4": 3},
            AssessmentScheme.NEWS_H1_H4,
            escalation_candidates=[flag],
        )
        assert result.category == "На заметку"
        assert result.final_category == "На заметку"
        assert result.escalation_flags == []


class TestRelevance:
    def test_relevance_derived_from_applicability(self) -> None:
        """Релевантность выводится из К1, а не запрашивается отдельным вызовом."""
        irrelevant = score(
            {"К1": 0, "К2": 3, "К3": 3, "К4": 3, "К5": 3, "К6": 3},
            AssessmentScheme.NPA_K1_K6,
        )
        assert irrelevant.is_relevant is False

        relevant = score(
            {"К1": 1, "К2": 0, "К3": 0, "К4": 0, "К5": 0, "К6": 0},
            AssessmentScheme.NPA_K1_K6,
        )
        assert relevant.is_relevant is True

    def test_news_relevance_uses_h2(self) -> None:
        result = score({"Н1": 3, "Н2": 0, "Н3": 3, "Н4": 3}, AssessmentScheme.NEWS_H1_H4)
        assert result.is_relevant is False


class TestValidation:
    @pytest.mark.parametrize(
        "scores,message",
        [
            ({"К1": 3, "К2": 2, "К3": 3, "К4": 0, "К5": 0}, "отсутствуют"),
            ({"К1": 4, "К2": 2, "К3": 3, "К4": 0, "К5": 0, "К6": 3}, "вне диапазона"),
            ({"К1": -1, "К2": 2, "К3": 3, "К4": 0, "К5": 0, "К6": 3}, "вне диапазона"),
            ({"К1": 2.5, "К2": 2, "К3": 3, "К4": 0, "К5": 0, "К6": 3}, "целым"),
        ],
    )
    def test_bad_scores_rejected(self, scores: dict, message: str) -> None:
        """Плохие баллы не превращаются в тихо неверный индекс."""
        with pytest.raises(ScoringError, match=message):
            score(scores, AssessmentScheme.NPA_K1_K6)

    def test_unknown_criterion_rejected(self) -> None:
        with pytest.raises(ScoringError, match="неизвестные"):
            score(
                {"К1": 3, "К2": 2, "К3": 3, "К4": 0, "К5": 0, "К6": 3, "К7": 1},
                AssessmentScheme.NPA_K1_K6,
            )


class TestConfigIntegrity:
    def test_weights_sum_to_one(self) -> None:
        config = get_scoring_config()
        for scheme in (config.npa, config.news):
            assert abs(sum(c.weight for c in scheme.criteria) - 1.0) < 1e-6

    def test_thresholds_match_methodology(self) -> None:
        """Пороги шкалы взяты из методики заказчика, а не назначены нами."""
        npa = [c.min_score for c in get_scoring_config().npa.ordered_categories]
        assert npa == [0, 25, 50, 75, 90]
        news = [c.min_score for c in get_scoring_config().news.ordered_categories]
        assert news == [0, 25, 50, 75]


class TestVerifyFormulaCli:
    def _write_dataset(self, path: Path, **overrides) -> None:
        import json

        row = {
            "id": 999,
            "kind": "act",
            "gold_scores": {"К1": 0, "К2": 0, "К3": 0, "К4": 0, "К5": 0, "К6": 0},
            "gold_index": 0.0,
            "gold_category": "Незначительное",
            "gold_escalation": False,
            "gold_final_category": "Незначительное",
        }
        row.update(overrides)
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_verify_formula_cli_exits_nonzero_on_index_mismatch(self, tmp_path: Path) -> None:
        dataset = tmp_path / "registry.jsonl"
        self._write_dataset(dataset, gold_index=1.0)

        result = CliRunner().invoke(app, ["verify-formula", "--dataset", str(dataset)])

        assert result.exit_code == 1
        assert "Index mismatches: 1" in result.output

    def test_verify_formula_cli_exits_nonzero_on_base_category_mismatch(self, tmp_path: Path) -> None:
        dataset = tmp_path / "registry.jsonl"
        self._write_dataset(dataset, gold_category="Низкое")

        result = CliRunner().invoke(app, ["verify-formula", "--dataset", str(dataset)])

        assert result.exit_code == 1
        assert "Category mismatches: 1" in result.output

    def test_verify_formula_cli_exits_nonzero_on_final_category_mismatch(self, tmp_path: Path) -> None:
        dataset = tmp_path / "registry.jsonl"
        self._write_dataset(dataset, gold_final_category="Высокое")

        result = CliRunner().invoke(app, ["verify-formula", "--dataset", str(dataset)])

        assert result.exit_code == 1
        assert "Final category mismatches: 1" in result.output

    def test_verify_formula_cli_exits_nonzero_on_read_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.jsonl"

        result = CliRunner().invoke(app, ["verify-formula", "--dataset", str(missing)])

        assert result.exit_code == 1
        assert "Не удалось прочитать эталон" in result.output
