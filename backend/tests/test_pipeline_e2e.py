"""Сквозной сценарий US1: материал → саммари с заземлением → классификация → оценка.

Модель подставная: тест проверяет наш конвейер и границу «модель предлагает,
код решает», а не качество чужого сервиса.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.contracts import (
    ClaimVerdict,
    ClassifyResult,
    DedupPairResult,
    ScoreResultRaw,
    SummarizeResult,
    VerifyClaimsResult,
)
from src.llm.provider import LLMError
from src.models import Assessment, Author, CompanyProfile, Item, ItemType, Revision, Topic
from src.pipeline.runner import process_item
from src.scoring import get_scoring_config


class StubProvider:
    """Отвечает заготовками по идентификатору промпта."""

    name = "stub"
    model = "stub-model"

    def __init__(self, **overrides) -> None:
        self.calls: list[str] = []
        self.users: list[tuple[str, str]] = []
        self.overrides = overrides
        self.fail_on: set[str] = set()

    async def complete_json(self, prompt_id, system, user, schema):
        self.calls.append(prompt_id)
        self.users.append((prompt_id, user))
        if prompt_id in self.fail_on:
            raise LLMError(f"смоделированный отказ на {prompt_id}")
        if prompt_id in self.overrides:
            return self.overrides[prompt_id]

        if prompt_id.startswith("summarize"):
            return SummarizeResult.model_validate(
                {
                    "claims": [
                        {
                            "statement": "Государственная Дума приняла закон об ИИ",
                            "quote": "Государственная Дума приняла закон о поддержке технологий",
                        },
                        {
                            "statement": "Маркировка обязательна с 1 марта 2027 года",
                            "quote": "Маркировка контента становится обязательной с 1 марта 2027 года",
                        },
                    ],
                    "entities": {
                        "who": ["Государственная Дума"],
                        "what": "Принят закон об ИИ",
                        "when": "1 марта 2027",
                        "consequences": "Обязательная маркировка контента",
                    },
                }
            )
        if prompt_id.startswith("verify_claims"):
            return VerifyClaimsResult(
                verdicts=[ClaimVerdict(index=0, entailed=True), ClaimVerdict(index=1, entailed=True)]
            )
        if prompt_id.startswith("classify"):
            return ClassifyResult(
                topic=Topic.REGULATORY, act_identifier="ФЗ № 243-ФЗ"
            )
        if prompt_id.startswith("dedup"):
            return DedupPairResult(relation="unrelated", reason="в тесте один материал")
        if prompt_id.startswith("score_npa"):
            return ScoreResultRaw(
                scores={"К1": 3, "К2": 3, "К3": 1, "К4": 1, "К5": 0, "К6": 0},
                rationales={code: f"обоснование {code}" for code in ("К1", "К2", "К3", "К4", "К5", "К6")},
                escalation_candidates=[],
            )
        raise AssertionError(f"неожиданный промпт {prompt_id}")


@pytest.mark.asyncio
async def test_full_pipeline_produces_grounded_and_scored_card(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    provider = StubProvider()
    result = await process_item(session, item, provider, profile)
    await session.commit()

    assert result.summarized and result.classified and result.scored

    summary = item.current_summary
    assert summary is not None
    assert len(summary.accepted_claims) == 2
    assert "Государственная Дума приняла закон об ИИ." in summary.text
    assert summary.prompt_version == "summarize/v1"
    assert provider.calls[:4] == ["summarize/v1", "verify_claims/v1", "classify/v1", "score_npa/v1"]

    assessment = item.current_assessment
    assert assessment is not None
    # Индекс посчитан кодом по методике заказчика, а не пришёл от модели.
    assert assessment.index_value == 51.7
    assert assessment.category == "Среднее"
    assert assessment.final_category == "Среднее"
    assert assessment.author == Author.AI
    assert item.item_type == ItemType.ACT
    assert "Тип материала (задан источником): act" in dict(provider.users)["classify/v1"]
    assert item.is_relevant is True
    assert item.processed_at is not None


@pytest.mark.asyncio
async def test_model_cannot_set_category_directly(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    """Даже если модель попытается назвать категорию, код её не примет.

    В контракте ScoreResultRaw поля категории нет вовсе — принцип II конституции.
    """
    assert "category" not in ScoreResultRaw.model_fields
    assert "index_value" not in ScoreResultRaw.model_fields

    provider = StubProvider()
    await process_item(session, item, provider, profile)
    assessment = item.current_assessment
    assert assessment is not None
    # Категория выведена из индекса, а индекс — из баллов.
    scheme = get_scoring_config().npa
    expected = next(
        c.name for c in reversed(scheme.ordered_categories) if assessment.index_value >= c.min_score
    )
    assert assessment.category == expected


@pytest.mark.asyncio
async def test_ungrounded_claim_never_reaches_summary(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    """Утверждение с выдуманной цитатой отбрасывается, но остаётся видимым в счётчике."""
    provider = StubProvider(
        **{
            "summarize/v1": SummarizeResult.model_validate(
                {
                    "claims": [
                        {
                            "statement": "Закон вводит штрафы до миллиона рублей",
                            "quote": "предусмотрены штрафы в размере до одного миллиона рублей",
                        },
                        {
                            "statement": "Закон принят Государственной Думой",
                            "quote": "Государственная Дума приняла закон",
                        },
                    ],
                    "entities": {"who": [], "what": "", "when": "", "consequences": ""},
                }
            ),
            "verify_claims/v1": VerifyClaimsResult(verdicts=[ClaimVerdict(index=0, entailed=True)]),
        }
    )
    await process_item(session, item, provider, profile)

    summary = item.current_summary
    assert summary is not None
    assert "штраф" not in summary.text.lower(), "выдуманный факт попал в саммари"
    assert len(summary.claims) == 2, "отбракованное утверждение должно сохраняться"
    assert len(summary.rejected_claims) == 1


@pytest.mark.asyncio
async def test_semantically_rejected_claim_never_reaches_summary_or_scoring(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    """Настоящая цитата с неверным смыслом отбрасывается до классификации и оценки."""
    provider = StubProvider(
        **{
            "summarize/v1": SummarizeResult.model_validate(
                {
                    "claims": [
                        {
                            "statement": "Государственная Дума приняла закон об ИИ",
                            "quote": "Государственная Дума приняла закон о поддержке технологий",
                        },
                        {
                            "statement": "Закон вводит уголовную ответственность за дипфейки",
                            "quote": "Маркировка контента становится обязательной с 1 марта 2027 года",
                        },
                    ],
                    "entities": {"who": [], "what": "", "when": "", "consequences": ""},
                }
            ),
            "verify_claims/v1": VerifyClaimsResult(
                verdicts=[
                    ClaimVerdict(index=0, entailed=True),
                    ClaimVerdict(
                        index=1,
                        entailed=False,
                        reason="Цитата говорит о маркировке, а не об уголовной ответственности.",
                    ),
                ]
            ),
        }
    )

    await process_item(session, item, provider, profile)

    summary = item.current_summary
    assert summary is not None
    assert "Государственная Дума приняла закон об ИИ." in summary.text
    assert "уголовн" not in summary.text.lower()
    assert summary.rejected_claims[0]["reject_reason"] == "not_entailed"
    downstream_payloads = [
        user for prompt_id, user in provider.users if prompt_id in {"classify/v1", "score_npa/v1"}
    ]
    assert downstream_payloads
    assert all("уголовную ответственность" not in user for user in downstream_payloads)


@pytest.mark.asyncio
async def test_failed_scoring_keeps_item_in_feed(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    """Отказ модели на оценке не теряет материал — он попадает в ленту с пометкой."""
    provider = StubProvider()
    provider.fail_on = {"score_npa/v1"}

    result = await process_item(session, item, provider, profile)
    await session.commit()

    assert result.scored is False
    assert item.assessment_failed is True
    assert item.current_summary is not None, "саммари должно остаться"
    assert item.current_assessment is None


@pytest.mark.asyncio
async def test_user_edits_survive_reprocessing(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    """FR-043, SC-012: переобработка не затирает правки пользователя.

    Это ровно тот дефект, который есть в драфте news_parser: там топики удалялись
    при каждом пересчёте, и правка исчезала через час.
    """
    provider = StubProvider()
    await process_item(session, item, provider, profile)
    await session.commit()

    # Человек правит саммари и тематику.
    machine_summary = item.current_summary.text
    machine_assessment = item.current_assessment
    assert machine_assessment is not None
    for existing in item.summaries:
        existing.is_current = False
    for existing in item.assessments:
        existing.is_current = False
    from src.models import Summary

    session.add(
        Summary(item_id=item.id, text="Моя формулировка сути", author=Author.HUMAN, is_current=True)
    )
    session.add(
        Revision(entity_type="summary", entity_id=item.id, field="text", author=Author.HUMAN)
    )
    session.add(
        Revision(entity_type="item", entity_id=item.id, field="topic", author=Author.HUMAN)
    )
    session.add(
        Assessment(
            item_id=item.id,
            profile_id=profile.id,
            scheme=machine_assessment.scheme,
            scores={**machine_assessment.scores, "К1": 0},
            rationales=machine_assessment.rationales,
            index_value=26.7,
            category="Низкое",
            escalation_flags=[],
            final_category="Низкое",
            author=Author.HUMAN,
            is_current=True,
        )
    )
    session.add(
        Revision(
            entity_type="assessment",
            entity_id=item.id,
            field="scores",
            old_value=machine_assessment.scores,
            new_value={**machine_assessment.scores, "К1": 0},
            author=Author.HUMAN,
        )
    )
    item.topic = Topic.COMPETITORS
    await session.commit()
    await session.refresh(item, ["summaries"])

    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(item, ["summaries"])

    assert "summary" in result.skipped_fields
    assert "classification" in result.skipped_fields
    assert "assessment" in result.skipped_fields
    assert item.current_summary.text == "Моя формулировка сути"
    assert item.current_summary.text != machine_summary
    assert item.topic == Topic.COMPETITORS
    assert item.current_assessment.author == Author.HUMAN
    assert item.current_assessment.scores["К1"] == 0
    # Машинная версия не удалена — пользователь может сравнить.
    assert any(s.author == Author.AI for s in item.summaries)
