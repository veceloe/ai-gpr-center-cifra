"""Кеш ответов модели — research R-06.

Ключ: sha256(prompt_id + модель + нормализованный вход). Повторный прогон тех же
материалов не обращается к сети. Две причины: демонстрация не должна зависеть от
доступности API, и замер SC-003 не должен упираться в лимиты провайдера.

Замер производительности выполняется с ВЫКЛЮЧЕННЫМ кешем — иначе цифра лжёт.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from threading import Lock

from src.config import DATA_DIR


def cache_key(prompt_id: str, model: str, payload: str) -> str:
    normalized = " ".join(payload.split())
    raw = f"{prompt_id}\x00{model}\x00{normalized}".encode()
    return hashlib.sha256(raw).hexdigest()


class ResponseCache:
    """Простой SQLite-кеш. Синхронный: обращения короткие, блокировка дешевле пула."""

    def __init__(self, path: Path | None = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._path = path or (DATA_DIR / "llm_cache.db")
        self._lock = Lock()
        self._init()

    def _init(self) -> None:
        with self._lock, sqlite3.connect(self._path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache ("
                " key TEXT PRIMARY KEY,"
                " prompt_id TEXT NOT NULL,"
                " model TEXT NOT NULL,"
                " response TEXT NOT NULL,"
                " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def get(self, key: str) -> dict | None:
        with self._lock, sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:  # pragma: no cover - повреждённая запись
            return None

    def put(self, key: str, prompt_id: str, model: str, response: dict) -> None:
        with self._lock, sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, prompt_id, model, response) VALUES (?, ?, ?, ?)",
                (key, prompt_id, model, json.dumps(response, ensure_ascii=False)),
            )

    def clear(self) -> None:
        with self._lock, sqlite3.connect(self._path) as conn:
            conn.execute("DELETE FROM llm_cache")
