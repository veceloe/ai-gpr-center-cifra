"""Клиент к LLM через LangChain (ChatDeepSeek)."""

import logging
from typing import TypeVar

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LlmClient:
    """Клиент к DeepSeek с поддержкой структурированного вывода через with_structured_output."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model = ChatDeepSeek(
            api_key=settings.llm_api_key or "no-key",
            api_base=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            # Внутренний LLM-шлюз отдаётся по HTTPS на IP с самоподписанным сертификатом.
            http_async_client=httpx.AsyncClient(verify=False),
            http_client=httpx.Client(verify=False),
        )

    async def chat_structured(self, system: str, user: str, schema: type[T]) -> T:
        """Делает вызов LLM и возвращает ответ, провалидированный по pydantic-схеме."""
        model = self._model.with_structured_output(schema)
        logger.debug("LLM structured request: model=%s schema=%s", self._model.model_name, schema.__name__)
        return await model.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=user),
            ]
        )
