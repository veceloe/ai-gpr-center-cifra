"""Приведение собранного материала к единому виду — FR-006."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Признаки того, что доступен только анонс: Ведомости и Коммерсантъ отдают часть
# материалов по подписке (граничный случай из spec.md). Влияет на заземление —
# проверять цитаты можно только по доступному фрагменту.
PARTIAL_TEXT_MARKERS = (
    "продолжение доступно",
    "читать далее в",
    "полный текст доступен",
    "подпишитесь, чтобы",
    "для подписчиков",
    "материал доступен подписчикам",
)
MIN_FULL_TEXT_LENGTH = 400

_WHITESPACE = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(raw: str) -> str:
    """Убирает мусорные пробелы, сохраняя абзацы: они нужны для читаемости цитат."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()


def extract_from_html(html: str) -> str:
    """Извлекает основной текст страницы.

    trafilatura опционален: без него работает запасной путь на selectolax, чтобы
    отсутствие тяжёлой зависимости не ломало сбор целиком.
    """
    try:
        import trafilatura

        extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
        if extracted:
            return clean_text(extracted)
    except ImportError:  # pragma: no cover - зависимость объявлена в requirements
        logger.debug("trafilatura недоступна, использую selectolax")
    except Exception as exc:
        logger.warning("trafilatura не справилась: %s", str(exc)[:200])

    try:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        for tag in tree.css("script, style, nav, header, footer, aside"):
            tag.decompose()
        body = tree.body
        return clean_text(body.text(separator="\n")) if body else ""
    except Exception as exc:
        logger.warning("Не удалось извлечь текст: %s", str(exc)[:200])
        return ""


def content_hash(text: str) -> str:
    """Хеш нормализованного текста: тот же URL с изменившимся текстом — новая версия."""
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def detect_partial_text(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in PARTIAL_TEXT_MARKERS):
        return True
    return len(text) < MIN_FULL_TEXT_LENGTH


def resolve_published_at(candidate: datetime | None) -> tuple[datetime, bool]:
    """Возвращает (дата, признак приближения).

    Источник без даты не отбрасывается: материал принимается с датой сбора, но
    пользователь видит, что дата приблизительная (граничный случай из spec.md).
    """
    if candidate is None:
        return datetime.now(UTC), True
    if candidate.tzinfo is None:
        return candidate.replace(tzinfo=UTC), False
    return candidate.astimezone(UTC), False
