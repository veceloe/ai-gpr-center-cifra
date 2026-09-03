from __future__ import annotations

import logging
from collections import deque
from collections.abc import Sequence
from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from src.llm.cache import ResponseCache, cache_key
from src.llm.contracts import (
    ClaimVerdict,
    ClassifyResult,
    DedupPairResult,
    ScoreResultRaw,
    SummarizeResult,
    VerifyClaimsResult,
)
from src.llm.prompts import CLASSIFY, DEDUP_PAIR, SUMMARIZE, VERIFY_CLAIMS, build_score_prompt
from src.llm.provider import FallbackProvider, LLMError, OpenAICompatibleProvider
from src.models import AssessmentScheme, ItemType, Topic
from src.scoring import get_scoring_config


class FakeHTTPResponse:
    def __init__(self, *, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    def __init__(self, outcomes: deque[FakeHTTPResponse | Exception], calls: list[dict]) -> None:
        self._outcomes = outcomes
        self._calls = calls

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def post(self, url: str, *, json: dict, headers: dict) -> FakeHTTPResponse:
        self._calls.append({"url": url, "json": json, "headers": headers})
        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def chat_response(content: str) -> FakeHTTPResponse:
    return FakeHTTPResponse(
        status_code=200,
        payload={"choices": [{"message": {"content": content}}]},
    )


def install_fake_http(
    monkeypatch: pytest.MonkeyPatch, outcomes: Sequence[FakeHTTPResponse | Exception]
) -> list[dict]:
    calls: list[dict] = []
    shared_outcomes = deque(outcomes)

    def factory(**_kwargs: object) -> FakeAsyncClient:
        return FakeAsyncClient(shared_outcomes, calls)

    monkeypatch.setattr("src.llm.provider.httpx.AsyncClient", factory)
    return calls


def provider(*, cache: ResponseCache | None = None, max_retries: int = 1) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="primary",
        base_url="https://llm.example/v1",
        model="model-a",
        api_key="sk-test-api-key",
        temperature=0.0,
        timeout=3.0,
        verify_tls=True,
        max_retries=max_retries,
        cache=cache,
    )


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, result: object | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def complete_json(self, prompt_id: str, system: str, user: str, schema: type):
        self.calls.append(prompt_id)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_primary_provider_returns_structured_pydantic_response(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_http(
        monkeypatch,
        [
            chat_response(
                '{"claims":[{"statement":"Закон принят","quote":"Государственная Дума приняла закон"}],'
                '"entities":{"who":["Государственная Дума"],"what":"Принят закон"}}'
            )
        ],
    )

    result = await provider(max_retries=0).complete_json(
        SUMMARIZE.id,
        SUMMARIZE.system,
        "Текст материала",
        SummarizeResult,
    )

    assert isinstance(result, SummarizeResult)
    assert result.claims[0].statement == "Закон принят"
    assert result.entities.who == ["Государственная Дума"]
    assert calls[0]["url"] == "https://llm.example/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test-api-key"
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_invalid_structured_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_http(monkeypatch, [chat_response('{"item_type":"unknown","topic":"regulatory"}')])

    with pytest.raises(LLMError, match="не прошёл валидацию"):
        await provider(max_retries=0).complete_json(
            CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
        )


@pytest.mark.asyncio
async def test_provider_retries_once_after_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_http(
        monkeypatch,
        [
            chat_response('{"item_type":"unknown","topic":"regulatory"}'),
            chat_response('{"item_type":"act","topic":"regulatory","act_identifier":"  ФЗ № 1  "}'),
        ],
    )

    result = await provider(max_retries=1).complete_json(
        CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
    )

    assert result == ClassifyResult(
        item_type=ItemType.ACT, topic=Topic.REGULATORY, act_identifier="ФЗ № 1"
    )
    assert len(calls) == 2
    retry_messages = calls[1]["json"]["messages"]
    assert retry_messages[-1]["role"] == "user"
    assert "валидацию схемы" in retry_messages[-1]["content"]


@pytest.mark.asyncio
async def test_provider_respects_retry_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_http(
        monkeypatch,
        [
            chat_response('{"item_type":"unknown","topic":"regulatory"}'),
            chat_response('{"item_type":"still-bad","topic":"regulatory"}'),
        ],
    )

    with pytest.raises(LLMError):
        await provider(max_retries=1).complete_json(
            CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
        )

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_fallback_provider_uses_reserve_after_primary_error() -> None:
    fallback_result = ClassifyResult(item_type=ItemType.NEWS, topic=Topic.TRENDS)
    primary = FakeProvider(error=httpx.ReadTimeout("timeout"))
    fallback = FakeProvider(result=fallback_result)

    result = await FallbackProvider(primary, fallback).complete_json(
        CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
    )

    assert result == fallback_result
    assert primary.calls == [CLASSIFY.id]
    assert fallback.calls == [CLASSIFY.id]


@pytest.mark.asyncio
async def test_fallback_provider_raises_when_both_providers_fail() -> None:
    primary = FakeProvider(error=httpx.ConnectError("primary down"))
    fallback = FakeProvider(error=LLMError("fallback invalid"))

    with pytest.raises(LLMError, match="fallback invalid"):
        await FallbackProvider(primary, fallback).complete_json(
            CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
        )

    assert primary.calls == [CLASSIFY.id]
    assert fallback.calls == [CLASSIFY.id]


@pytest.mark.asyncio
async def test_timeout_from_primary_provider_is_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_http(monkeypatch, [httpx.ReadTimeout("request timed out")])

    with pytest.raises(httpx.ReadTimeout, match="timed out"):
        await provider(max_retries=0).complete_json(
            CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
        )


@pytest.mark.asyncio
async def test_cache_miss_calls_remote_provider(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls = install_fake_http(
        monkeypatch,
        [chat_response('{"item_type":"news","topic":"trends","act_identifier":null}')],
    )

    result = await provider(cache=ResponseCache(tmp_path / "llm.db"), max_retries=0).complete_json(
        CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
    )

    assert result.item_type is ItemType.NEWS
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cache_hit_does_not_call_remote_provider(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    cache = ResponseCache(tmp_path / "llm.db")
    calls = install_fake_http(
        monkeypatch,
        [chat_response('{"item_type":"news","topic":"trends","act_identifier":null}')],
    )
    llm = provider(cache=cache, max_retries=0)

    first = await llm.complete_json(CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult)
    second = await llm.complete_json(CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult)

    assert first == second
    assert len(calls) == 1


def test_cache_key_is_stable_normalized_and_partitioned() -> None:
    first = cache_key("summarize/v1", "model-a", "same   input\ntext")
    second = cache_key("summarize/v1", "model-a", "same input text")

    assert first == second
    assert len(first) == 64
    assert all(char in "0123456789abcdef" for char in first)
    assert first != cache_key("summarize/v2", "model-a", "same input text")
    assert first != cache_key("summarize/v1", "model-b", "same input text")
    assert first != cache_key("summarize/v1", "model-a", "different input text")
    assert cache_key("ab", "c", "d") != cache_key("a", "bc", "d")


def test_cache_entries_are_not_shared_across_prompt_model_or_input(tmp_path) -> None:
    cache = ResponseCache(tmp_path / "llm.db")
    original = cache_key("classify/v1", "model-a", "input")
    cache.put(original, "classify/v1", "model-a", {"item_type": "news", "topic": "trends"})

    assert cache.get(original) == {"item_type": "news", "topic": "trends"}
    assert cache.get(cache_key("classify/v2", "model-a", "input")) is None
    assert cache.get(cache_key("classify/v1", "model-b", "input")) is None
    assert cache.get(cache_key("classify/v1", "model-a", "other input")) is None


@pytest.mark.parametrize(
    "scores",
    [
        {"К1": -1},
        {"К1": 4},
        {"К1": True},
        {"К1": 1.5},
    ],
)
def test_score_contract_rejects_scores_outside_allowed_range(scores: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScoreResultRaw.model_validate({"scores": scores})


def test_score_contract_never_accepts_model_computed_index_or_category() -> None:
    result = ScoreResultRaw.model_validate(
        {
            "scores": {"К1": 1},
            "rationales": {"К1": "Есть связь с профилем."},
            "index_value": 100,
            "category": "Критическое",
        }
    )

    assert result.scores == {"К1": 1}
    assert "index_value" not in ScoreResultRaw.model_fields
    assert "category" not in ScoreResultRaw.model_fields


def test_prompt_ids_cover_current_llm_contract() -> None:
    config = get_scoring_config()
    score_news = build_score_prompt(
        AssessmentScheme.NEWS_H1_H4, config, "Профиль компании", date(2026, 9, 3)
    )
    score_npa = build_score_prompt(
        AssessmentScheme.NPA_K1_K6, config, "Профиль компании", date(2026, 9, 3)
    )

    assert SUMMARIZE.id == "summarize/v1"
    assert VERIFY_CLAIMS.id == "verify_claims/v1"
    assert CLASSIFY.id == "classify/v1"
    assert DEDUP_PAIR.id == "dedup_pair/v1"
    assert score_news.id == "score_news/v1"
    assert score_npa.id == "score_npa/v1"
    assert "Сегодняшняя дата: 2026-09-03" in score_news.system
    assert "Не определяй итоговую категорию" in score_npa.system


def test_remaining_contract_models_validate_synthetic_payloads() -> None:
    verify = VerifyClaimsResult.model_validate(
        {"verdicts": [{"index": 0, "entailed": True, "reason": "Цитата подтверждает."}]}
    )
    dedup = DedupPairResult.model_validate({"relation": "same_fact", "reason": "Один факт."})

    assert verify.verdicts == [
        ClaimVerdict(index=0, entailed=True, reason="Цитата подтверждает.")
    ]
    assert dedup.relation == "same_fact"


@pytest.mark.asyncio
async def test_api_key_is_not_exposed_in_logs_or_exceptions(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install_fake_http(
        monkeypatch,
        [
            FakeHTTPResponse(
                status_code=500,
                text="upstream unavailable",
            )
        ],
    )
    caplog.set_level(logging.WARNING)

    with pytest.raises(LLMError) as exc_info:
        await provider(max_retries=0).complete_json(
            CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
        )

    assert "sk-test-api-key" not in str(exc_info.value)
    assert "sk-test-api-key" not in caplog.text
