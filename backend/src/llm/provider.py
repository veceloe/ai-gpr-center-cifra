"""Доступ к модели — ADR-0006.

Интерфейс `LLMProvider` с двумя реализациями: основной и резервной. Живое демо не
должно зависеть от доступности одного API — отказ сети в момент защиты обнуляет
всю работу.

Ответ валидируется по pydantic-схеме, при провале выполняется один повтор с явным
указанием нарушенного поля. После повторной неудачи вызывающий код помечает материал
`assessment_failed` — материал попадает в ленту без оценки, но не теряется.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from src.config import Settings, get_settings
from src.llm.cache import ResponseCache, cache_key

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Модель не дала пригодного ответа ни с первой попытки, ни с повтора."""


class LLMProvider(Protocol):
    """Контракт, к которому обращается весь пайплайн."""

    name: str
    model: str

    async def complete_json(self, prompt_id: str, system: str, user: str, schema: type[T]) -> T: ...


class OpenAICompatibleProvider:
    """Chat Completions с ответом в JSON.

    Совместим с OpenAI, OpenRouter, vLLM, Ollama и любым сервисом с тем же контрактом:
    менять провайдера — значит менять переменные окружения, а не код.
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float,
        timeout: float,
        verify_tls: bool,
        max_retries: int,
        cache: ResponseCache | None,
    ) -> None:
        self.name = name
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._temperature = temperature
        self._timeout = timeout
        self._verify_tls = verify_tls
        self._max_retries = max_retries
        self._cache = cache

    async def complete_json(self, prompt_id: str, system: str, user: str, schema: type[T]) -> T:
        key = cache_key(prompt_id, self.model, system + "\x00" + user)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                logger.debug("LLM cache hit: %s", prompt_id)
                return schema.model_validate(cached)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            started = time.perf_counter()
            raw = await self._request(messages)
            elapsed = time.perf_counter() - started
            try:
                parsed = json.loads(raw)
                result = schema.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.warning(
                    "LLM %s: невалидный ответ на %s (попытка %s/%s): %s",
                    self.name,
                    prompt_id,
                    attempt + 1,
                    self._max_retries + 1,
                    str(exc)[:300],
                )
                # Повтор с явным указанием, что именно нарушено: без этого модель
                # повторяет ту же ошибку.
                messages = [
                    *messages,
                    {"role": "assistant", "content": raw[:2000]},
                    {
                        "role": "user",
                        "content": (
                            "Ответ не прошёл валидацию схемы. Ошибка:\n"
                            f"{str(exc)[:800]}\n\n"
                            "Верни ТОЛЬКО валидный JSON нужной формы, без пояснений и без markdown."
                        ),
                    },
                ]
                continue

            logger.info(
                "LLM %s: %s за %.2f с (модель %s)", self.name, prompt_id, elapsed, self.model
            )
            if self._cache is not None:
                self._cache.put(key, prompt_id, self.model, result.model_dump(mode="json"))
            return result

        raise LLMError(f"{self.name}: ответ на {prompt_id} не прошёл валидацию") from last_error

    async def _request(self, messages: list[dict]) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify_tls) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=body, headers=headers
            )
            if response.status_code >= 400:
                raise LLMError(
                    f"{self.name}: HTTP {response.status_code} от {self._base_url}: {response.text[:300]}"
                )
            payload = response.json()

        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name}: неожиданная форма ответа API") from exc


class FallbackProvider:
    """Основной провайдер с автоматическим переходом на резервный.

    Переключение только на сетевых и серверных сбоях. Ошибку валидации схемы
    резервный провайдер не исправит — она означает проблему промпта, а не канала.
    """

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback
        self.name = f"{primary.name}→{fallback.name}"
        self.model = primary.model

    async def complete_json(self, prompt_id: str, system: str, user: str, schema: type[T]) -> T:
        try:
            return await self._primary.complete_json(prompt_id, system, user, schema)
        except (httpx.HTTPError, LLMError) as exc:
            logger.warning(
                "Основной провайдер %s недоступен (%s) — переключаюсь на %s",
                self._primary.name,
                str(exc)[:200],
                self._fallback.name,
            )
            result = await self._fallback.complete_json(prompt_id, system, user, schema)
            self.model = self._fallback.model
            return result


def build_provider(settings: Settings | None = None) -> LLMProvider:
    cfg = settings or get_settings()
    cache = ResponseCache() if cfg.llm_cache_enabled else None

    primary = OpenAICompatibleProvider(
        name="primary",
        base_url=cfg.llm_base_url,
        model=cfg.llm_model,
        api_key=cfg.llm_api_key,
        temperature=cfg.llm_temperature,
        timeout=cfg.llm_timeout_seconds,
        verify_tls=cfg.llm_verify_tls,
        max_retries=cfg.llm_max_retries,
        cache=cache,
    )

    if not cfg.llm_fallback_configured:
        return primary

    fallback = OpenAICompatibleProvider(
        name="fallback",
        base_url=cfg.llm_fallback_base_url,
        model=cfg.llm_fallback_model,
        api_key=cfg.llm_fallback_api_key,
        temperature=cfg.llm_temperature,
        timeout=cfg.llm_timeout_seconds,
        verify_tls=cfg.llm_verify_tls,
        max_retries=cfg.llm_max_retries,
        cache=cache,
    )
    return FallbackProvider(primary, fallback)
