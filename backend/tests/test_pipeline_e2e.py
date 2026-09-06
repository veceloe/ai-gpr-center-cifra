"""Сквозной сценарий US1: материал → саммари с заземлением → классификация → оценка.

Модель подставная: тест проверяет наш конвейер и границу «модель предлагает,
код решает», а не качество чужого сервиса.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.base import CollectedItem, _upsert_item
from src.llm.contracts import (
    ActLifecycleResult,
    ClaimVerdict,
    ClassifyResult,
    DedupPairResult,
    ScoreResultRaw,
    SummarizeResult,
    VerifyClaimsResult,
)
from src.llm.provider import LLMError
from src.models import (
    Act,
    ActEvent,
    ActEventType,
    ActStage,
    Assessment,
    Author,
    CompanyProfile,
    Item,
    ItemType,
    Revision,
    Story,
    Topic,
)
from src.pipeline.runner import process_item
from src.scoring import get_scoring_config


def item_text() -> str:
    return (
        "Государственная Дума приняла закон о поддержке технологий искусственного "
        "интеллекта. Документ вводит режим для больших фундаментальных моделей "
        "с числом параметров не менее одного миллиарда. Маркировка контента "
        "становится обязательной с 1 марта 2027 года."
    )


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
            override = self.overrides[prompt_id]
            if isinstance(override, list):
                if not override:
                    raise AssertionError(f"ответы для {prompt_id} закончились")
                return override.pop(0)
            return override

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
        if prompt_id.startswith("act_lifecycle"):
            return ActLifecycleResult(
                stage_candidate=None,
                confidence=0.0,
                evidence_quote=None,
                rationale="явная стадия не найдена",
            )
        if prompt_id.startswith("dedup"):
            return DedupPairResult(relation="unrelated", reason="в тесте один материал")
        if prompt_id.startswith("score_npa"):
            return ScoreResultRaw(
                scores={"К1": 3, "К2": 3, "К3": 1, "К4": 1, "К5": 0, "К6": 0},
                rationales={code: f"обоснование {code}" for code in ("К1", "К2", "К3", "К4", "К5", "К6")},
                escalation_candidates=[],
            )
        if prompt_id.startswith("score_news"):
            return ScoreResultRaw(
                scores={"Н1": 3, "Н2": 3, "Н3": 1, "Н4": 1},
                rationales={code: f"обоснование {code}" for code in ("Н1", "Н2", "Н3", "Н4")},
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
    assert provider.calls[:5] == [
        "summarize/v1",
        "verify_claims/v1",
        "classify/v1",
        "act_lifecycle/v1",
        "score_npa/v1",
    ]

    assessment = item.current_assessment
    assert assessment is not None
    # Индекс посчитан кодом по методике заказчика, а не пришёл от модели.
    assert assessment.index_value == 51.7
    assert assessment.category == "Среднее"
    assert assessment.final_category == "Среднее"
    assert assessment.author == Author.AI
    assert item.item_type == ItemType.ACT
    assert "Тип материала (задан источником): act" in dict(provider.users)["classify/v1"]
    assert result.act_identifier == "ФЗ № 243-ФЗ"
    assert item.is_relevant is True
    assert item.processed_at is not None


@pytest.mark.asyncio
async def test_collected_act_item_type_selects_npa_scoring(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    source.item_type = ItemType.ACT
    candidate = CollectedItem(
        url="https://duma.example/document/act",
        title="Проект федерального закона",
        raw_text=item_text(),
    )
    assert await _upsert_item(session, source, candidate) == "created"
    stored = await session.scalar(select(Item).where(Item.url == candidate.url))
    assert stored is not None

    provider = StubProvider()
    await process_item(session, stored, provider, profile)

    assert stored.item_type == ItemType.ACT
    assert "score_npa/v1" in provider.calls
    assert "score_news/v1" not in provider.calls


@pytest.mark.asyncio
async def test_collected_news_item_type_selects_news_scoring(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    source.item_type = ItemType.NEWS
    candidate = CollectedItem(
        url="https://media.example/news/1",
        title="Отраслевая новость",
        raw_text=item_text(),
    )
    assert await _upsert_item(session, source, candidate) == "created"
    stored = await session.scalar(select(Item).where(Item.url == candidate.url))
    assert stored is not None

    provider = StubProvider()
    await process_item(session, stored, provider, profile)

    assert stored.item_type == ItemType.NEWS
    assert "score_news/v1" in provider.calls
    assert "score_npa/v1" not in provider.calls
    assert "act_lifecycle/v1" not in provider.calls


@pytest.mark.asyncio
async def test_classify_response_cannot_retype_act_item(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    provider = StubProvider(
        **{
            "classify/v1": ClassifyResult.model_validate(
                {
                    "topic": "regulatory",
                    "act_identifier": "Законопроект № 1215252-8",
                    "item_type": "news",
                }
            )
        }
    )

    result = await process_item(session, item, provider, profile)

    assert item.item_type == ItemType.ACT
    assert result.act_identifier == "Законопроект № 1215252-8"
    assert "score_npa/v1" in provider.calls
    assert "score_news/v1" not in provider.calls


@pytest.mark.asyncio
async def test_act_identifier_links_act_item_to_existing_act(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    act = Act(
        act_identifier="ФЗ № 243-ФЗ",
        doc_type="Федеральный закон",
        stage=ActStage.SUBMITTED,
        source_url="https://duma.example/document/243",
        essence="Поддержка технологий искусственного интеллекта.",
    )
    session.add(act)
    await session.commit()

    provider = StubProvider()
    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(item)

    assert result.act_identifier == "ФЗ № 243-ФЗ"
    assert item.act_id == act.id
    assert item.story_id is None
    assert "dedup_pair/v1" not in provider.calls


@pytest.mark.asyncio
async def test_act_identifier_creates_minimal_act_for_first_act_item(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    provider = StubProvider()

    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(item)

    act = await session.scalar(select(Act).where(Act.act_identifier == "ФЗ № 243-ФЗ"))
    assert act is not None
    assert result.act_identifier == "ФЗ № 243-ФЗ"
    assert item.act_identifier == "ФЗ № 243-ФЗ"
    assert item.act_id == act.id
    assert item.story_id is None
    assert act.doc_type == "НПА"
    assert act.stage == ActStage.ANNOUNCEMENT
    assert act.source_url == item.url
    assert act.is_tracked is False

    event = await session.scalar(select(ActEvent).where(ActEvent.act_id == act.id))
    assert event is not None
    assert event.event_type == ActEventType.OTHER
    assert event.source_item_id == item.id
    assert event.document_url == item.url
    assert "dedup_pair/v1" not in provider.calls


@pytest.mark.asyncio
async def test_generic_llm_identifier_uses_regulation_project_id(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    item = Item(
        source_id=source.id,
        url="https://regulation.gov.ru/projects/170865/",
        title="Проект приказа",
        raw_text=item_text(),
        content_hash="regulation-170865",
        item_type=ItemType.ACT,
        published_at=datetime(2026, 9, 1, tzinfo=UTC),
        tags=[],
    )
    session.add(item)
    await session.commit()
    provider = StubProvider(
        **{"classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier="Приказ")}
    )

    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(item)

    assert result.act_identifier == "regulation.gov.ru:170865"
    assert item.act_identifier == "regulation.gov.ru:170865"
    act = await session.scalar(select(Act).where(Act.act_identifier == "regulation.gov.ru:170865"))
    assert act is not None
    assert item.act_id == act.id


@pytest.mark.asyncio
async def test_generic_llm_identifier_uses_sozd_bill_number(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    item = Item(
        source_id=source.id,
        url="https://sozd.duma.gov.ru/bill/835251-8",
        title="Проект постановления",
        raw_text=item_text(),
        content_hash="sozd-835251-8",
        item_type=ItemType.ACT,
        published_at=datetime(2026, 9, 1, tzinfo=UTC),
        tags=[],
    )
    session.add(item)
    await session.commit()
    provider = StubProvider(
        **{
            "classify/v1": ClassifyResult(
                topic=Topic.REGULATORY, act_identifier="Проект постановления"
            )
        }
    )

    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(item)

    assert result.act_identifier == "sozd.duma.gov.ru:835251-8"
    assert item.act_identifier == "sozd.duma.gov.ru:835251-8"
    act = await session.scalar(select(Act).where(Act.act_identifier == "sozd.duma.gov.ru:835251-8"))
    assert act is not None
    assert item.act_id == act.id


@pytest.mark.asyncio
async def test_different_regulation_project_ids_create_different_acts(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    for project_id in ("170865", "170866"):
        session.add(
            Item(
                source_id=source.id,
                url=f"https://regulation.gov.ru/projects/{project_id}/",
                title=f"Проект приказа {project_id}",
                raw_text=item_text(),
                content_hash=f"regulation-{project_id}",
                item_type=ItemType.ACT,
                published_at=datetime(2026, 9, 1, tzinfo=UTC),
                tags=[],
            )
        )
    await session.commit()
    provider = StubProvider(
        **{"classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier="Приказ")}
    )

    items = list((await session.execute(select(Item).order_by(Item.id))).scalars())
    for item in items:
        await process_item(session, item, provider, profile)
    await session.commit()

    identifiers = {
        act.act_identifier for act in (await session.execute(select(Act))).scalars()
    }
    assert identifiers == {"regulation.gov.ru:170865", "regulation.gov.ru:170866"}


@pytest.mark.asyncio
async def test_same_regulation_project_id_links_to_one_act(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    urls = [
        "https://regulation.gov.ru/projects/170865/",
        "https://www.regulation.gov.ru/projects/170865/?from=feed",
    ]
    for index, url in enumerate(urls):
        session.add(
            Item(
                source_id=source.id,
                url=url,
                title=f"Проект приказа {index}",
                raw_text=item_text(),
                content_hash=f"regulation-same-{index}",
                item_type=ItemType.ACT,
                published_at=datetime(2026, 9, 1, tzinfo=UTC),
                tags=[],
            )
        )
    await session.commit()
    provider = StubProvider(
        **{"classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier="Приказ")}
    )

    items = list((await session.execute(select(Item).order_by(Item.id))).scalars())
    for item in items:
        await process_item(session, item, provider, profile)
    await session.commit()

    acts = list((await session.execute(select(Act))).scalars())
    assert len(acts) == 1
    for item in items:
        await session.refresh(item)
        assert item.act_identifier == "regulation.gov.ru:170865"
        assert item.act_id == acts[0].id


@pytest.mark.asyncio
async def test_two_act_items_with_same_identifier_link_to_same_act(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    for index in range(2):
        session.add(
            Item(
                source_id=source.id,
                url=f"https://duma.example/document/243/{index}",
                title=f"Карточка НПА {index}",
                raw_text=item_text(),
                content_hash=f"act-{index}",
                item_type=ItemType.ACT,
                published_at=datetime(2026, 9, 1, tzinfo=UTC),
                tags=[],
            )
        )
    await session.commit()

    items = list((await session.execute(select(Item).order_by(Item.id))).scalars().all())
    provider = StubProvider()
    for stored in items:
        await process_item(session, stored, provider, profile)
    await session.commit()

    acts = list((await session.execute(select(Act))).scalars().all())
    assert len(acts) == 1
    act = acts[0]
    for stored in items:
        await session.refresh(stored)
        assert stored.act_id == act.id
        assert stored.story_id is None
        assert stored.act_identifier == "ФЗ № 243-ФЗ"
    events = list((await session.execute(select(ActEvent))).scalars().all())
    assert len(events) == 1
    assert "dedup_pair/v1" not in provider.calls


@pytest.mark.asyncio
async def test_missing_act_identifier_does_not_fail_pipeline(
    session: AsyncSession, item: Item, profile: CompanyProfile
) -> None:
    provider = StubProvider(
        **{"classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier=None)}
    )

    result = await process_item(session, item, provider, profile)

    assert result.classified is True
    assert result.act_identifier is not None
    assert result.act_identifier.startswith("url:")
    assert item.act_identifier == result.act_identifier
    assert item.act_id is not None
    assert "score_npa/v1" in provider.calls


@pytest.mark.asyncio
async def test_act_lifecycle_advances_stage_from_structured_outputs(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    stage_quotes = [
        (ActStage.ANNOUNCEMENT, "Опубликован анонс проекта требований к операторам связи."),
        (ActStage.DRAFT_DISCUSSION, "Проект проходит общественное обсуждение до 15 сентября."),
        (ActStage.SUBMITTED, "Проект внесён в Государственную Думу."),
        (ActStage.READINGS, "Законопроект проходит первое чтение."),
        (ActStage.ADOPTED, "Приказ принят уполномоченным органом."),
        (ActStage.IN_FORCE, "Приказ вступил в силу с 1 марта 2027 года."),
    ]
    for index, (_stage, quote) in enumerate(stage_quotes, start=1):
        session.add(
            Item(
                source_id=source.id,
                url=f"https://regulation.gov.ru/projects/999001/?stage={index}",
                title=f"TEST НПА lifecycle {index}",
                raw_text=f"{quote} {item_text()}",
                content_hash=f"act-lifecycle-{index}",
                item_type=ItemType.ACT,
                published_at=datetime(2026, 9, index, tzinfo=UTC),
                tags=[],
            )
        )
    await session.commit()

    provider = StubProvider(
        **{
            "classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier="Проект"),
            "act_lifecycle/v1": [
                ActLifecycleResult(
                    stage_candidate=stage,
                    confidence=0.92,
                    evidence_quote=quote,
                    rationale="цитата явно описывает текущую стадию",
                )
                for stage, quote in stage_quotes
            ],
        }
    )
    items = list((await session.execute(select(Item).order_by(Item.id))).scalars())
    for stored in items:
        await process_item(session, stored, provider, profile)
        await session.commit()

    acts = list((await session.execute(select(Act))).scalars())
    assert len(acts) == 1
    act = acts[0]
    assert act.act_identifier == "regulation.gov.ru:999001"
    assert act.stage == ActStage.IN_FORCE

    for stored in items:
        await session.refresh(stored)
        assert stored.act_id == act.id
        assert stored.act_identifier == "regulation.gov.ru:999001"

    events = list(
        (
            await session.execute(
                select(ActEvent)
                .where(ActEvent.event_type == ActEventType.STAGE_CHANGE)
                .order_by(ActEvent.id)
            )
        )
        .scalars()
        .all()
    )
    assert [event.source_item_id for event in events] == [item.id for item in items[1:]]
    assert [event.document_url for event in events] == [item.url for item in items[1:]]


@pytest.mark.asyncio
async def test_act_lifecycle_does_not_roll_stage_back(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    act = Act(
        act_identifier="regulation.gov.ru:999001",
        doc_type="НПА",
        stage=ActStage.ADOPTED,
        source_url="https://regulation.gov.ru/projects/999001/",
        essence="Проект уже принят.",
    )
    quote = "Проект проходит общественное обсуждение до 15 сентября."
    item = Item(
        source_id=source.id,
        url="https://regulation.gov.ru/projects/999001/?old=discussion",
        title="Старый материал об обсуждении",
        raw_text=f"{quote} {item_text()}",
        content_hash="act-lifecycle-no-rollback",
        item_type=ItemType.ACT,
        published_at=datetime(2026, 9, 1, tzinfo=UTC),
        tags=[],
    )
    session.add_all([act, item])
    await session.commit()

    provider = StubProvider(
        **{
            "classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier="Проект"),
            "act_lifecycle/v1": ActLifecycleResult(
                stage_candidate=ActStage.DRAFT_DISCUSSION,
                confidence=0.95,
                evidence_quote=quote,
                rationale="цитата описывает обсуждение",
            ),
        }
    )
    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(act)
    await session.refresh(item)

    assert result.act_stage_candidate == ActStage.DRAFT_DISCUSSION
    assert act.stage == ActStage.ADOPTED
    assert item.act_id == act.id
    assert (
        await session.scalar(
            select(ActEvent).where(ActEvent.event_type == ActEventType.STAGE_CHANGE)
        )
    ) is None


@pytest.mark.asyncio
async def test_act_lifecycle_null_candidate_does_not_change_stage(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    act = Act(
        act_identifier="regulation.gov.ru:999001",
        doc_type="НПА",
        stage=ActStage.SUBMITTED,
        source_url="https://regulation.gov.ru/projects/999001/",
        essence="Проект внесён.",
    )
    item = Item(
        source_id=source.id,
        url="https://regulation.gov.ru/projects/999001/?noise=1",
        title="Материал без явной новой стадии",
        raw_text=item_text(),
        content_hash="act-lifecycle-null",
        item_type=ItemType.ACT,
        published_at=datetime(2026, 9, 2, tzinfo=UTC),
        tags=[],
    )
    session.add_all([act, item])
    await session.commit()

    provider = StubProvider(
        **{
            "classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier="Проект"),
            "act_lifecycle/v1": ActLifecycleResult(
                stage_candidate=None,
                confidence=0.0,
                evidence_quote=None,
                rationale="явная стадия не найдена",
            ),
        }
    )
    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(act)

    assert result.act_stage_candidate is None
    assert act.stage == ActStage.SUBMITTED


@pytest.mark.asyncio
async def test_act_lifecycle_missing_evidence_quote_does_not_change_stage(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    act = Act(
        act_identifier="regulation.gov.ru:999001",
        doc_type="НПА",
        stage=ActStage.SUBMITTED,
        source_url="https://regulation.gov.ru/projects/999001/",
        essence="Проект внесён.",
    )
    item = Item(
        source_id=source.id,
        url="https://regulation.gov.ru/projects/999001/?bad-quote=1",
        title="Материал с неподтверждённой стадией",
        raw_text=item_text(),
        content_hash="act-lifecycle-bad-quote",
        item_type=ItemType.ACT,
        published_at=datetime(2026, 9, 3, tzinfo=UTC),
        tags=[],
    )
    session.add_all([act, item])
    await session.commit()

    provider = StubProvider(
        **{
            "classify/v1": ClassifyResult(topic=Topic.REGULATORY, act_identifier="Проект"),
            "act_lifecycle/v1": ActLifecycleResult(
                stage_candidate=ActStage.ADOPTED,
                confidence=0.91,
                evidence_quote="Приказ принят уполномоченным органом.",
                rationale="цитата не входит в raw_text и должна быть отброшена",
            ),
        }
    )
    result = await process_item(session, item, provider, profile)
    await session.commit()
    await session.refresh(act)

    assert result.act_stage_candidate == ActStage.ADOPTED
    assert act.stage == ActStage.SUBMITTED
    assert (
        await session.scalar(
            select(ActEvent).where(ActEvent.event_type == ActEventType.STAGE_CHANGE)
        )
    ) is None


@pytest.mark.asyncio
async def test_news_flow_skips_act_lifecycle_and_still_clusters_story(
    session: AsyncSession, source, profile: CompanyProfile
) -> None:
    source.item_type = ItemType.NEWS
    for index in range(2):
        session.add(
            Item(
                source_id=source.id,
                url=f"https://media.example/news/cluster-{index}",
                title=f"Госдума приняла закон об ИИ [{index}]",
                raw_text=item_text(),
                content_hash=f"news-lifecycle-cluster-{index}",
                item_type=ItemType.NEWS,
                published_at=datetime(2026, 9, index + 1, tzinfo=UTC),
                tags=[],
            )
        )
    await session.commit()

    provider = StubProvider(
        **{
            "dedup_pair/v1": DedupPairResult(
                relation="same_fact", reason="один и тот же факт"
            )
        }
    )
    items = list((await session.execute(select(Item).order_by(Item.id))).scalars())
    for stored in items:
        await process_item(session, stored, provider, profile)
        await session.commit()

    stories = list((await session.execute(select(Story))).scalars())
    assert "act_lifecycle/v1" not in provider.calls
    assert len(stories) == 1
    assert stories[0].item_count == 2
    for stored in items:
        await session.refresh(stored)
        assert stored.story_id == stories[0].id
        assert stored.act_id is None


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
