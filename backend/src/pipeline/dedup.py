"""Инкрементальная кластеризация дублей — FR-060, FR-061, T100.

Порядок гейтов важен и дешёвый идёт первым:
1. окно 10 дней, не весь архив одним вызовом;
2. векторная близость заголовка и первых предложений;
3. минимум две общие сущности;
4. только потом dedup_pair/v1 — объединение строго при same_fact.

Кластер Story создаётся один раз и дополняется. Пересчёт не удаляет его
и не меняет идентификатор — иначе правки пользователя пропадают (T099).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.llm.contracts import DedupPairResult
from src.llm.prompts import DEDUP_PAIR, dedup_user_message
from src.llm.provider import LLMError, LLMProvider
from src.models import Author, Item, Revision, Story
from src.pipeline.embed import cosine, embed, fingerprint_text

logger = logging.getLogger(__name__)

WINDOW_DAYS = 10
# Порог — предотбор, не решение: перефразы («Минцифры поддержало» vs
# «министерство выступило за») должны дойти до dedup_pair. Решение — у модели.
SIMILARITY_THRESHOLD = 0.28
MIN_SHARED_ENTITIES = 2
_TOKEN = re.compile(r"[а-яёa-z0-9-]{3,}", re.IGNORECASE)
_GENERIC = frozenset(
    {
        "когда",
        "после",
        "этот",
        "этой",
        "этого",
        "также",
        "между",
        "через",
        "года",
        "году",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
        "январь",
        "февраль",
        "март",
        "апрель",
        "июнь",
        "июль",
        "август",
        "май",
    }
)


def entity_tokens(entities: Any, title: str = "") -> set[str]:
    """Именованные сущности who/what — не заголовок и не календарь (T100)."""
    values: list[str] = []
    if isinstance(entities, dict):
        who = entities.get("who") or []
        if isinstance(who, str):
            who = [who]
        values.extend(str(item) for item in who)
        if entities.get("what"):
            values.append(str(entities["what"]))
    if not values and title:
        values.append(title)
    tokens: set[str] = set()
    for value in values:
        tokens.update(
            token.lower()
            for token in _TOKEN.findall(value)
            if token.lower() not in _GENERIC and not token.isdigit()
        )
    return tokens


def shared_entity_count(left: Item, right: Item) -> int:
    left_summary = left.current_summary
    right_summary = right.current_summary
    return len(
        entity_tokens(left_summary.entities if left_summary else {}, left.title)
        & entity_tokens(right_summary.entities if right_summary else {}, right.title)
    )


def _item_fingerprint(item: Item) -> str:
    summary = item.current_summary
    body = summary.text if summary and summary.text else item.raw_text
    return fingerprint_text(item.title, body)


async def _split_pairs(session: AsyncSession) -> set[frozenset[int]]:
    """Пары, которые пользователь уже разъединял, повторно не склеиваем."""
    values = (
        await session.execute(
            select(Revision.old_value).where(
                Revision.entity_type == "story",
                Revision.field == "split",
                Revision.author != Author.AI,
            )
        )
    ).scalars().all()
    pairs: set[frozenset[int]] = set()
    for value in values:
        ids = [int(item_id) for item_id in value] if isinstance(value, list) else []
        for index, left in enumerate(ids):
            for right in ids[index + 1 :]:
                pairs.add(frozenset((left, right)))
    return pairs


async def _window_items(session: AsyncSession, item: Item) -> list[Item]:
    since = (item.published_at or datetime.now(UTC)) - timedelta(days=WINDOW_DAYS)
    until = (item.published_at or datetime.now(UTC)) + timedelta(days=WINDOW_DAYS)
    return list(
        (
            await session.execute(
                select(Item)
                .where(
                    Item.id != item.id,
                    Item.published_at >= since,
                    Item.published_at <= until,
                    Item.is_hidden.is_(False),
                )
                .options(
                    selectinload(Item.summaries),
                    selectinload(Item.story),
                    selectinload(Item.source),
                )
            )
        )
        .scalars()
        .all()
    )


def _ranked_candidates(
    item: Item,
    others: list[Item],
    forbidden: set[frozenset[int]],
) -> list[Item]:
    vector = embed(_item_fingerprint(item))
    ranked: list[tuple[float, Item]] = []
    for other in others:
        if frozenset((item.id, other.id)) in forbidden:
            continue
        if other.story is not None and other.story.was_split_by_user:
            continue
        if shared_entity_count(item, other) < MIN_SHARED_ENTITIES:
            continue
        score = cosine(vector, embed(_item_fingerprint(other)))
        if score >= SIMILARITY_THRESHOLD:
            ranked.append((score, other))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _score, candidate in ranked]


async def _recount(session: AsyncSession, story: Story) -> Story:
    await session.refresh(story, ["items"])
    story.item_count = len(story.items)
    return story


async def _story_of(session: AsyncSession, item: Item) -> Story | None:
    """Связь story в той же сессии часто остаётся старой после flush — смотрим id."""
    if item.story is not None:
        return item.story
    if item.story_id is None:
        return None
    return await session.get(Story, item.story_id)


async def _attach(session: AsyncSession, item: Item, other: Item, reason: str) -> Story:
    left = await _story_of(session, item)
    right = await _story_of(session, other)

    # Два уже существующих кластера про одно событие склеиваем в более ранний:
    # иначе при догоне отставших материалов сюжет распадается на два Story.
    if left is not None and right is not None and left.id != right.id:
        keep, drop = (left, right) if left.id <= right.id else (right, left)
        await session.refresh(drop, ["items"])
        for member in list(drop.items):
            member.story_id = keep.id
        drop.item_count = 0
        if not keep.fact_summary:
            keep.fact_summary = reason
        item.story_id = keep.id
        item.story = keep
        other.story_id = keep.id
        other.story = keep
        await session.flush()
        return await _recount(session, keep)

    story = right or left
    if story is None:
        story = Story(
            canonical_title=other.title or item.title,
            fact_summary=reason,
            first_seen_at=min(item.published_at, other.published_at),
            item_count=0,
        )
        session.add(story)
        await session.flush()
    elif not story.fact_summary:
        story.fact_summary = reason

    for member in (item, other):
        member.story_id = story.id
        member.story = story
    await session.flush()
    return await _recount(session, story)


async def cluster_item(
    session: AsyncSession,
    item: Item,
    provider: LLMProvider,
) -> Story | None:
    """Пытается присоединить материал к существующему событию или создать новое."""
    await session.refresh(item, ["summaries", "story", "source"])
    forbidden = await _split_pairs(session)
    candidates = _ranked_candidates(item, await _window_items(session, item), forbidden)
    summary = item.current_summary.text if item.current_summary else item.raw_text[:500]

    story = await _story_of(session, item)
    for candidate in candidates:
        candidate_story = await _story_of(session, candidate)
        if story is not None and candidate_story is not None and story.id == candidate_story.id:
            continue
        other_summary = (
            candidate.current_summary.text if candidate.current_summary else candidate.raw_text[:500]
        )
        try:
            verdict = await provider.complete_json(
                DEDUP_PAIR.id,
                DEDUP_PAIR.system,
                dedup_user_message(item.title, summary, candidate.title, other_summary),
                DedupPairResult,
            )
        except LLMError as exc:
            logger.warning(
                "Item %s: кандидат %s пропущен — %s",
                item.id,
                candidate.id,
                str(exc)[:200],
            )
            continue

        if verdict.relation != "same_fact":
            logger.info(
                "Item %s не объединяем с %s: %s (%s)",
                item.id,
                candidate.id,
                verdict.relation,
                verdict.reason,
            )
            continue

        story = await _attach(session, item, candidate, verdict.reason)
        logger.info(
            "Item %s добавлен в Story %s (%s материалов)", item.id, story.id, story.item_count
        )
    return story


async def split_story(
    session: AsyncSession,
    story: Story,
    *,
    reason: str | None = None,
) -> None:
    """Разъединяет кластер и запоминает пары, чтобы пайплайн их не склеил снова."""
    await session.refresh(story, ["items"])
    members = list(story.items)
    item_ids = [member.id for member in members]
    story.items.clear()
    for member in members:
        member.story_id = None
    story.was_split_by_user = True
    story.item_count = 0
    session.add(
        Revision(
            entity_type="story",
            entity_id=story.id,
            field="split",
            old_value=item_ids,
            new_value=[],
            author=Author.HUMAN,
            reason=reason,
        )
    )
