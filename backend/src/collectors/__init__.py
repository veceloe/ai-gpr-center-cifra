"""Сбор материалов из источников.

Импорт модулей регистрирует адаптеры в общем реестре, поэтому он обязателен здесь,
а не по требованию: `get_adapter` должен знать обо всех типах сразу.
"""

from src.collectors import rss, sozd, telegram, web  # noqa: F401 - регистрация адаптеров
from src.collectors.base import (
    CollectedItem,
    CollectResult,
    SourceAdapter,
    collect_active_sources,
    collect_source,
    get_adapter,
    register_adapter,
)

__all__ = [
    "CollectResult",
    "CollectedItem",
    "SourceAdapter",
    "collect_active_sources",
    "collect_source",
    "get_adapter",
    "register_adapter",
]
