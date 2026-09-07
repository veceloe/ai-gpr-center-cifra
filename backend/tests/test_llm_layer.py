from __future__ import annotations

import logging
from collections import deque
from collections.abc import Sequence
from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from src.config import Settings
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
from src.llm.provider import (
    FallbackProvider,
    LLMError,
    OpenAICompatibleProvider,
    RoutingProvider,
    build_provider,
)
from src.models import AssessmentScheme, Topic
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
    install_fake_http(monkeypatch, [chat_response('{"topic":"unknown"}')])

    with pytest.raises(LLMError, match="не прошёл валидацию"):
        await provider(max_retries=0).complete_json(
            CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
        )


@pytest.mark.asyncio
async def test_provider_retries_once_after_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_http(
        monkeypatch,
        [
            chat_response('{"topic":"unknown"}'),
            chat_response('{"topic":"regulatory","act_identifier":"  ФЗ № 1  "}'),
        ],
    )

    result = await provider(max_retries=1).complete_json(
        CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
    )

    assert result == ClassifyResult(topic=Topic.REGULATORY, act_identifier="ФЗ № 1")
    assert len(calls) == 2
    retry_messages = calls[1]["json"]["messages"]
    assert retry_messages[-1]["role"] == "user"
    assert "валидацию схемы" in retry_messages[-1]["content"]


@pytest.mark.asyncio
async def test_provider_respects_retry_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_fake_http(
        monkeypatch,
        [
            chat_response('{"topic":"unknown"}'),
            chat_response('{"topic":"still-bad"}'),
        ],
    )

    with pytest.raises(LLMError):
        await provider(max_retries=1).complete_json(
            CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
        )

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_fallback_provider_uses_reserve_after_primary_error() -> None:
    fallback_result = ClassifyResult(topic=Topic.TRENDS)
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
        [chat_response('{"topic":"trends","act_identifier":null}')],
    )

    result = await provider(cache=ResponseCache(tmp_path / "llm.db"), max_retries=0).complete_json(
        CLASSIFY.id, CLASSIFY.system, "input", ClassifyResult
    )

    assert result.topic is Topic.TRENDS
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cache_hit_does_not_call_remote_provider(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    cache = ResponseCache(tmp_path / "llm.db")
    calls = install_fake_http(
        monkeypatch,
        [chat_response('{"topic":"trends","act_identifier":null}')],
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
    cache.put(original, "classify/v1", "model-a", {"topic": "trends", "act_identifier": None})

    assert cache.get(original) == {"topic": "trends", "act_identifier": None}
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


def test_classify_contract_has_no_item_type_output() -> None:
    result = ClassifyResult.model_validate(
        {"topic": "regulatory", "act_identifier": "ФЗ № 1", "item_type": "news"}
    )

    assert result.topic is Topic.REGULATORY
    assert result.act_identifier == "ФЗ № 1"
    assert "item_type" not in ClassifyResult.model_fields
    assert not hasattr(result, "item_type")


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
    assert score_news.id == "score_news/v3"
    assert score_npa.id == "score_npa/v3"
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


def test_empty_scores_are_rejected_so_provider_retries() -> None:
    """Пустой набор баллов должен падать на контракте, а не позже.

    Иначе повтор запроса не срабатывает: контракт отвечает «валидно», а
    отбраковка происходит уже при подсчёте индекса, и материал остаётся
    без оценки из-за одного неудачного ответа модели.
    """
    with pytest.raises(ValidationError):
        ScoreResultRaw(scores={}, rationales={}, escalation_candidates=[])

    ok = ScoreResultRaw(scores={"К1": 2}, rationales={}, escalation_candidates=[])
    assert ok.scores == {"К1": 2}


def test_latin_lookalike_criterion_codes_are_normalized() -> None:
    """Латинские K и H приводятся к кириллическим К и Н.

    Модель иногда возвращает «K1» с латинской K вместо кириллической: JSON
    выглядит безупречно, а коды не совпадают ни с одним из наших, и материал
    молча остаётся без оценки. Найдено при сравнении моделей — три карточки
    из 42 у deepseek-v4-flash.
    """
    result = ScoreResultRaw(
        scores={"K1": 3, "K2": 0},
        rationales={"H1": "обоснование"},
        escalation_candidates=[],
    )
    assert list(result.scores) == ["К1", "К2"]
    assert [hex(ord(code[0])) for code in result.scores] == ["0x41a", "0x41a"]
    assert list(result.rationales) == ["Н1"]
    assert [hex(ord(code[0])) for code in result.rationales] == ["0x41d"]


def test_score_range_and_type_checks_survive_normalization() -> None:
    """Нормализация кодов не должна ослабить проверку самих баллов."""
    for bad in ({"K1": True}, {"К1": 9}, {"К1": "3"}):
        with pytest.raises(ValidationError):
            ScoreResultRaw(scores=bad, rationales={}, escalation_candidates=[])


class RecordingProvider:
    """Провайдер-протокол для проверки маршрутизации: помнит, что через него прошло."""

    def __init__(self, model: str) -> None:
        self.name = model
        self.model = model
        self.calls: list[str] = []

    async def complete_json(self, prompt_id: str, system: str, user: str, schema):
        self.calls.append(prompt_id)
        return schema.model_construct()


@pytest.mark.asyncio
async def test_routing_provider_sends_only_scoring_to_the_reasoning_model() -> None:
    """Оценка идёт на рассуждающую модель, остальные шаги — на быструю.

    Преимущество рассуждающей модели измерено только на оценке. Отправлять на
    неё саммари и заземление значит менять неизмеренное и терять право на уже
    полученные цифры заземления, а каждый её вызов стоит десятки секунд при
    бюджете SC-003 в 10-15 секунд на публикацию.
    """
    fast = RecordingProvider("fast-model")
    scoring = RecordingProvider("reasoning-model")
    provider = RoutingProvider(fast=fast, scoring=scoring)

    for prompt_id in ("summarize/v1", "verify_claims/v1", "classify/v1", "dedup_pair/v1"):
        await provider.complete_json(prompt_id, "s", "u", ClassifyResult)
    for prompt_id in ("score_npa/v3", "score_news/v3"):
        await provider.complete_json(prompt_id, "s", "u", ClassifyResult)

    assert fast.calls == ["summarize/v1", "verify_claims/v1", "classify/v1", "dedup_pair/v1"]
    assert scoring.calls == ["score_npa/v3", "score_news/v3"]
    assert provider.model == "reasoning-model", "модель последнего вызова видна снаружи"


def test_single_model_config_does_not_build_a_router() -> None:
    """Без указанной быстрой модели поведение прежнее — одна модель на конвейер."""
    cfg = Settings(
        llm_base_url="https://example.test/v1",
        llm_model="one-model",
        llm_api_key="k",
        llm_cache_enabled=False,
    )
    assert not isinstance(build_provider(cfg), RoutingProvider)
