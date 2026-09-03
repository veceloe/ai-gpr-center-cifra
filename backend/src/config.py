"""Настройки приложения.

Правило: ни одно поле, без которого нельзя запустить демо, не бывает обязательным.
Драфт news_parser не стартовал без S3-конфигурации — здесь такого быть не должно.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BACKEND_DIR / "config"
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Хранилище ---
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- LLM: основной провайдер ---
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 120.0
    llm_verify_tls: bool = True
    llm_max_retries: int = 1

    # --- LLM: резервный провайдер (ADR-0006) ---
    # Живое демо не должно зависеть от доступности одного API.
    llm_fallback_base_url: str = ""
    llm_fallback_model: str = ""
    llm_fallback_api_key: str = ""

    # Кеш ответов модели: повторный прогон тех же материалов не ходит в сеть.
    llm_cache_enabled: bool = True

    # --- Сбор ---
    poll_interval_media_min: int = 15
    poll_interval_regulator_min: int = 60
    fetch_limit_per_source: int = 50

    # --- Telegram (ADR-0008) ---
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_string_session: str = ""
    telegram_proxy: str = ""

    # --- Конфигурационные файлы ---
    scoring_config_path: Path = CONFIG_DIR / "scoring.yaml"
    company_profile_path: Path = CONFIG_DIR / "company_profile.yaml"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key.strip() or self.llm_base_url.startswith("http://localhost"))

    @property
    def llm_fallback_configured(self) -> bool:
        return bool(self.llm_fallback_base_url.strip() and self.llm_fallback_model.strip())

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_api_id and self.telegram_api_hash and self.telegram_string_session)


@lru_cache
def get_settings() -> Settings:
    return Settings()
