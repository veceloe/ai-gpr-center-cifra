"""Создание Telethon-клиента с опциональным прокси."""

import logging
from pathlib import Path
from urllib.parse import urlparse

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SUPPORTED_SCHEMES = frozenset({"http", "socks4", "socks5"})


def parse_proxy_url(raw: str) -> tuple | None:
    """
    http://host:port
    socks5://user:pass@host:port
    host:port  → http по умолчанию
    """
    value = raw.strip()
    if not value:
        return None

    if "://" not in value:
        value = f"http://{value}"

    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme == "https":
        scheme = "http"
    if scheme not in _SUPPORTED_SCHEMES:
        raise ValueError(f"Unsupported proxy scheme {scheme!r}. Use http, socks4 or socks5.")

    host = parsed.hostname
    if not host:
        raise ValueError(f"Invalid TELEGRAM_PROXY URL: {raw!r}")

    port = parsed.port
    if port is None:
        port = 8080 if scheme == "http" else 1080

    if parsed.username is not None:
        return (scheme, host, port, parsed.username, parsed.password or "")

    return (scheme, host, port)


def _proxy_kwargs(settings: Settings) -> dict:
    proxy = parse_proxy_url(settings.telegram_proxy)
    if proxy is None:
        return {}

    scheme, host, port, *auth = proxy
    logger.info(
        "Using proxy %s://%s:%s auth=%s",
        scheme,
        host,
        port,
        bool(auth),
    )
    # Telethon ждёт прокси как dict (или 6-кортеж с rdns). Раньше отдавался
    # 5-кортеж без rdns → username/password съезжали → proxy возвращал 407.
    proxy_dict: dict = {
        "proxy_type": scheme,
        "addr": host,
        "port": port,
        "rdns": True,
    }
    if auth:
        proxy_dict["username"] = auth[0]
        proxy_dict["password"] = auth[1] if len(auth) > 1 else ""
    return {"proxy": proxy_dict}


def create_telegram_client(
    session_path: str | Path,
    settings: Settings | None = None,
) -> TelegramClient:
    cfg = settings or get_settings()

    # Если задана готовая StringSession — используем её (k8s-деплой, без файла).
    if cfg.telegram_string_session.strip():
        session: str | StringSession = StringSession(cfg.telegram_string_session)
        logger.info("Using StringSession from config")
    else:
        path = Path(session_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        session = str(path)

    return TelegramClient(
        session,
        cfg.telegram_api_id,
        cfg.telegram_api_hash,
        **_proxy_kwargs(cfg),
    )
