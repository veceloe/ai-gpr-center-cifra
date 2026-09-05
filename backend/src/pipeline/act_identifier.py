"""Канонический ключ НПА для связывания материалов с Act."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote, urlparse

_REGULATION_PROJECT = re.compile(r"/projects/(?P<id>\d+)(?:/|$)")
_SOZD_BILL = re.compile(r"/bill/(?P<number>\d+-\d+)(?:/|$)")
_GENERIC_IDENTIFIERS = {
    "нпа",
    "приказ",
    "постановление",
    "проект",
    "проект нпа",
    "проект приказа",
    "проект постановления",
}


def canonical_act_identifier(raw_identifier: str | None, url: str) -> str | None:
    """Возвращает стабильный ключ Act, не позволяя общим словам стать identifier."""
    official = _official_identifier(url)
    if official:
        return official

    raw = raw_identifier.strip() if isinstance(raw_identifier, str) else ""
    if raw and not _is_generic(raw):
        return raw

    canonical_url = _canonical_url(url)
    if not canonical_url:
        return None
    digest = hashlib.sha256(canonical_url.encode()).hexdigest()[:16]
    return f"url:{digest}"


def _official_identifier(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = unquote(parsed.path)

    if host == "regulation.gov.ru":
        match = _REGULATION_PROJECT.search(path)
        if match:
            return f"regulation.gov.ru:{match.group('id')}"

    if host == "sozd.duma.gov.ru":
        match = _SOZD_BILL.search(path)
        if match:
            return f"sozd.duma.gov.ru:{match.group('number')}"

    return None


def _is_generic(identifier: str) -> bool:
    normalized = re.sub(r"[^а-яёa-z0-9]+", " ", identifier.lower()).strip()
    return normalized in _GENERIC_IDENTIFIERS


def _canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.netloc:
        return url.strip()
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+", "/", unquote(parsed.path)).rstrip("/")
    return f"{parsed.scheme.lower()}://{host}{path or '/'}"
