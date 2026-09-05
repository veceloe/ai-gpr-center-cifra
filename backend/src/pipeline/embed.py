"""Векторное представление заголовка и первых предложений — research R-05.

Внешний эмбеддинг-API сознательно не используется: отбор кандидатов должен
работать офлайн на ноутбуке команды и в тестах. Близость лексическая, различие
позиций ловит уже модель в dedup_pair.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"[а-яёa-z0-9]{3,}", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def fingerprint_text(title: str, body: str, sentences: int = 2) -> str:
    """Текст, по которому считаем близость: заголовок + первые предложения."""
    first = " ".join(_SENTENCE.split((body or "").strip())[:sentences])
    return f"{title.strip()} {first}".lower()


def embed(text: str) -> dict[str, float]:
    """Нормированный мешок символьных 3-грамм и слов."""
    normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
    counts: Counter[str] = Counter()
    padded = f" {normalized} "
    for index in range(max(len(padded) - 2, 0)):
        gram = padded[index : index + 3]
        if gram.strip():
            counts[f"g:{gram}"] += 1
    for word in _WORD.findall(normalized):
        counts[f"w:{word}"] += 1
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {key: value / norm for key, value in counts.items()}


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())
