"""Кластеризация дублей — FR-060, FR-061, FR-062, H-05, T075."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.contracts import DedupPairResult
from src.models import Author, Item, ItemType, Source, Story, Summary
from src.pipeline.dedup import (
    SIMILARITY_THRESHOLD,
    cluster_item,
    shared_entity_count,
    split_story,
)
from src.pipeline.embed import cosine, embed, fingerprint_text


class DedupStub:
    name = "stub"
    model = "stub-dedup"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, prompt_id, system, user, schema):
        self.calls.append((prompt_id, user))
        left = _event_from_user(user, "A")
        right = _event_from_user(user, "B")
        if left == right:
            return DedupPairResult(relation="same_fact", reason="один и тот же факт")
        if {left, right} == {"ministry", "association"}:
            return DedupPairResult(
                relation="different_positions",
                reason="Минцифры поддерживает законопроект, ассоциация выступает против.",
            )
        return DedupPairResult(relation="unrelated", reason="разные события")


def _event_from_user(user: str, side: str) -> str:
    match = re.search(rf"Материал {side}\nЗаголовок: (?P<title>.*?)\n", user)
    block = match.group("title").lower() if match else user.lower()
    if "[cas]" in block or "[ministry]" in block or "[association]" in block:
        if "[ministry]" in block:
            return "ministry"
        if "[association]" in block:
            return "association"
        return "cas"
    if "триколор" in block or "[tricolor]" in block:
        return "tricolor"
    if "рфрит" in block or "грант" in block or "[grants]" in block:
        return "grants"
    if "против" in block or "раскритик" in block or "вредн" in block:
        return "association"
    if "поддерж" in block or "выступило за" in block or "позиция минцифры" in block:
        return "ministry"
    if "cas" in block or "drm" in block:
        return "cas"
    raise AssertionError(f"не размечен материал {side}: {block[:80]}")


def _entities(event: str) -> dict:
    shared_bill = {
        "who": ["Государственная Дума", "Минцифры"],
        "what": "Законопроект о CAS и DRM",
        "when": "сентябрь 2026",
        "consequences": "Переход операторов на российские системы доступа",
    }
    catalog = {
        "cas": shared_bill,
        "ministry": shared_bill,
        "association": shared_bill,
        "tricolor": {
            "who": ["Триколор"],
            "what": "Новый пакет телеканалов",
            "when": "сентябрь 2026",
            "consequences": "Расширение сетки вещания",
        },
        "grants": {
            "who": ["РФРИТ"],
            "what": "Грантовая программа для разработчиков ПО",
            "when": "2026",
            "consequences": "Финансирование пилотов",
        },
    }
    return catalog[event]


CONTROL = (
    ("cas", "Госдума внесла законопроект о переходе на российские CAS и DRM [{n}]"),
    ("cas", "В Госдуму внесён законопроект о российских CAS/DRM [{n}]"),
    ("cas", "Законопроект о CAS и DRM поступил в Государственную Думу [{n}]"),
    ("cas", "Депутаты внесли в Думу проект об обязательных российских CAS [{n}]"),
    ("cas", "Проект закона о замене иностранных CAS направлен в Госдуму [{n}]"),
    ("ministry", "Минцифры поддержало законопроект о российских CAS и DRM [{n}]"),
    ("ministry", "Минцифры выступило за законопроект о российских CAS и DRM [{n}]"),
    ("ministry", "Позиция Минцифры: законопроект о российских CAS и DRM нужен отрасли [{n}]"),
    ("association", "Ассоциация операторов выступила против законопроекта о CAS [{n}]"),
    ("association", "Отраслевая ассоциация раскритиковала проект CAS и DRM [{n}]"),
    ("association", "Ассоциация считает законопроект о CAS вредным для рынка [{n}]"),
    ("tricolor", "Триколор расширил пакет спортивных телеканалов [{n}]"),
    ("tricolor", "Триколор расширил пакет: новые спортивные телеканалы [{n}]"),
    ("tricolor", "Триколор добавил спортивные телеканалы в пакет [{n}]"),
    ("tricolor", "Пакет Триколора пополнился спортивными телеканалами [{n}]"),
    ("tricolor", "Триколор дал абонентам дополнительные спортивные телеканалы [{n}]"),
    ("grants", "РФРИТ открыл грантовую программу для разработчиков ПО [{n}]"),
    ("grants", "Фонд РФРИТ объявил гранты разработчикам программного обеспечения [{n}]"),
    ("grants", "Стартовала грантовая программа РФРИТ для российских разработчиков [{n}]"),
    ("grants", "РФРИТ начал приём заявок на гранты разработчикам ПО [{n}]"),
)


@pytest.mark.asyncio
async def test_control_sample_keeps_opposite_positions_apart(
    session: AsyncSession, source: Source
) -> None:
    """20 публикаций / 5 событий: повторы схлопнуты, противники закона — нет."""
    created: list[Item] = []
    counts: dict[str, int] = {}
    day = datetime(2026, 9, 1, tzinfo=UTC)
    for index, (event, title_tpl) in enumerate(CONTROL):
        counts[event] = counts.get(event, 0) + 1
        title = title_tpl.format(n=counts[event])
        item = Item(
            source_id=source.id,
            url=f"https://example.test/cluster/{index}",
            title=title,
            raw_text=f"{title}. Подробности события {event}.",
            content_hash=f"cluster-{index}",
            published_at=day + timedelta(hours=index),
            item_type=ItemType.NEWS,
            tags=[],
        )
        session.add(item)
        await session.flush()
        session.add(
            Summary(
                item_id=item.id,
                text=title,
                entities=_entities(event),
                author=Author.AI,
                is_current=True,
            )
        )
        created.append(item)
    await session.commit()
    for item in created:
        await session.refresh(item, ["summaries"])

    provider = DedupStub()
    for item in created:
        await cluster_item(session, item, provider)
    await session.commit()

    stories = list((await session.execute(select(Story))).scalars().all())
    grouped: dict[int, list[Item]] = {}
    for item in created:
        await session.refresh(item)
        if item.story_id:
            grouped.setdefault(item.story_id, []).append(item)

    assert len(created) == 20
    cas_ids = {item.story_id for item in created[:5]}
    assert None not in cas_ids and len(cas_ids) == 1
    assert len(grouped[next(iter(cas_ids))]) == 5

    ministry_ids = {item.story_id for item in created[5:8]}
    association_ids = {item.story_id for item in created[8:11]}
    assert None not in ministry_ids and len(ministry_ids) == 1
    assert None not in association_ids and len(association_ids) == 1
    assert not (ministry_ids & association_ids), "противников закона склеили с сторонниками"

    tricolor_ids = {item.story_id for item in created[11:16]}
    grants_ids = {item.story_id for item in created[16:]}
    assert None not in tricolor_ids and len(tricolor_ids) == 1
    assert None not in grants_ids and len(grants_ids) == 1
    assert next(iter(tricolor_ids)) != next(iter(grants_ids))
    assert {next(iter(ids)) for ids in (cas_ids, ministry_ids, association_ids, tricolor_ids, grants_ids)} == {
        story.id for story in stories
    }
    assert all(story.item_count >= 2 for story in stories)
    assert len(stories) == 5


@pytest.mark.asyncio
async def test_split_prevents_remerge(session: AsyncSession, source: Source) -> None:
    first, second = await _pair(session, source, "cas")
    provider = DedupStub()
    await cluster_item(session, first, provider)
    await cluster_item(session, second, provider)
    await session.commit()
    await session.refresh(first)
    assert first.story_id == second.story_id

    story = await session.get(Story, first.story_id)
    assert story is not None
    await split_story(session, story, reason="разные редакции")
    await session.commit()
    await session.refresh(first)
    await session.refresh(second)
    assert first.story_id is None and second.story_id is None
    assert story.was_split_by_user is True

    await cluster_item(session, first, provider)
    await cluster_item(session, second, provider)
    await session.commit()
    await session.refresh(first)
    await session.refresh(second)
    assert first.story_id is None and second.story_id is None


@pytest.mark.asyncio
async def test_process_backfills_clustering_for_summarized_items(
    session: AsyncSession, source: Source, profile
) -> None:
    from src.pipeline.runner import process_unprocessed

    first, second = await _pair(session, source, "cas")
    first.processed_at = datetime(2026, 9, 2, tzinfo=UTC)
    second.processed_at = datetime(2026, 9, 2, tzinfo=UTC)
    await session.commit()

    results = await process_unprocessed(session, DedupStub(), limit=5)
    await session.refresh(first)
    await session.refresh(second)
    assert first.story_id is not None and first.story_id == second.story_id
    assert any(result.clustered for result in results)


@pytest.mark.asyncio
async def test_entity_gate_blocks_unrelated_similar_wording(
    session: AsyncSession, source: Source
) -> None:
    left, right = await _pair(session, source, "cas", other_event="tricolor")
    assert shared_entity_count(left, right) < 2
    provider = DedupStub()
    await cluster_item(session, left, provider)
    await cluster_item(session, right, provider)
    await session.commit()
    await session.refresh(left)
    await session.refresh(right)
    assert left.story_id is None or left.story_id != right.story_id


def test_similarity_threshold_separates_unrelated_topics() -> None:
    same = cosine(
        embed(fingerprint_text("Госдума внесла законопроект о CAS и DRM", "Внесён проект.")),
        embed(fingerprint_text("В Госдуму внесён законопроект о российских CAS/DRM", "Проект внесён.")),
    )
    other = cosine(
        embed(fingerprint_text("Госдума внесла законопроект о CAS и DRM", "Внесён проект.")),
        embed(fingerprint_text("Триколор расширил пакет спортивных телеканалов", "Новые каналы.")),
    )
    assert same >= SIMILARITY_THRESHOLD
    assert other < SIMILARITY_THRESHOLD


async def _pair(
    session: AsyncSession,
    source: Source,
    event: str,
    other_event: str | None = None,
) -> tuple[Item, Item]:
    second_event = other_event or event
    items: list[Item] = []
    for index, current in enumerate((event, second_event)):
        title = f"Публикация [{current}] номер {index}"
        item = Item(
            source_id=source.id,
            url=f"https://example.test/pair/{current}/{index}",
            title=title,
            raw_text=title,
            content_hash=f"pair-{current}-{index}",
            published_at=datetime(2026, 9, 2, tzinfo=UTC),
            item_type=ItemType.NEWS,
            tags=[],
        )
        session.add(item)
        await session.flush()
        session.add(
            Summary(
                item_id=item.id,
                text=title,
                entities=_entities(current),
                author=Author.AI,
                is_current=True,
            )
        )
        items.append(item)
    await session.commit()
    for item in items:
        await session.refresh(item, ["summaries"])
    return items[0], items[1]
