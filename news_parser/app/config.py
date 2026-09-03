from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Period = Literal["day", "week", "month"]

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CHANNELS_CONFIG = ROOT_DIR / "config" / "channels.yaml"


class ChannelConfig(BaseModel):
    username: str
    title: str | None = None


class ChannelsFile(BaseModel):
    channels: list[ChannelConfig]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone: str
    telegram_session_path: str = "./data/telegram.session"
    # Готовая StringSession (для деплоя в k8s): если задана — используется вместо
    # файловой сессии, не нужен файл на диске/PVC. Генерится скриптом auth_telegram.
    telegram_string_session: str = ""

    # Прокси одной строкой: http://host:port, socks5://user:pass@host:port
    telegram_proxy: str = ""

    llm_api_key: str = Field(
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str = Field(
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    llm_model: str = Field(
        validation_alias=AliasChoices("LLM_MODEL", "OPENAI_MODEL"),
    )
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 120.0

    database_url: str = "sqlite+aiosqlite:///./data/news.db"

    parse_interval_minutes: int = 180
    fetch_limit_per_channel: int = 200
    topics_refresh_interval_minutes: int = 180

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    channels_config_path: str = Field(
        default=str(DEFAULT_CHANNELS_CONFIG),
        validation_alias="CHANNELS_CONFIG",
    )

    # --- S3 (Cloud.ru OBS) — берутся из CI/CD переменных ---
    s3_endpoint_url: str
    s3_bucket: str
    s3_prefix: str = "campaign/outer_news"
    s3_region: str = "ru-1"
    s3_access_key: str
    s3_secret_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_channels(config_path: Path | None = None) -> list[ChannelConfig]:
    path = config_path or Path(get_settings().channels_config_path)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ChannelsFile.model_validate(data).channels


def normalize_channel_username(username: str) -> str:
    value = username.strip()
    if value.startswith("https://t.me/"):
        value = value.removeprefix("https://t.me/").split("/")[0]
    return value.lstrip("@")
