"""Обработка материалов: нормализация, заземление, оценка."""

from src.pipeline.grounding import (
    RejectReason,
    build_summary_text,
    check_entailment,
    check_quotes,
    grounding_stats,
    locate_quote,
    normalize_with_map,
)
from src.pipeline.normalize import (
    clean_text,
    content_hash,
    detect_partial_text,
    extract_from_html,
    resolve_published_at,
)
from src.pipeline.runner import ProcessResult, get_active_profile, process_item, process_unprocessed

__all__ = [
    "ProcessResult",
    "RejectReason",
    "build_summary_text",
    "check_entailment",
    "check_quotes",
    "clean_text",
    "content_hash",
    "detect_partial_text",
    "extract_from_html",
    "get_active_profile",
    "grounding_stats",
    "locate_quote",
    "normalize_with_map",
    "process_item",
    "process_unprocessed",
    "resolve_published_at",
]
