"""Детерминированная часть оценки влияния."""

from src.scoring.config import (
    MAX_SCORE,
    MIN_SCORE,
    Criterion,
    SchemeConfig,
    ScoringConfig,
    get_scoring_config,
    load_scoring_config,
)
from src.scoring.formula import (
    ScoreResult,
    ScoringError,
    apply_escalation,
    compute_index,
    normalize_flags,
    resolve_category,
    score,
    validate_scores,
)

__all__ = [
    "MAX_SCORE",
    "MIN_SCORE",
    "Criterion",
    "SchemeConfig",
    "ScoreResult",
    "ScoringConfig",
    "ScoringError",
    "apply_escalation",
    "compute_index",
    "get_scoring_config",
    "load_scoring_config",
    "normalize_flags",
    "resolve_category",
    "score",
    "validate_scores",
]
