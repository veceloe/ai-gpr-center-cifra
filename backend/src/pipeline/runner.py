"""Пайплайн обработки материала: саммари → заземление → классификация → оценка → кластер.

Порядок неслучаен. Классификация опирается на саммари и определяет только тему
и идентификатор НПА; схема оценки выбирается по Item.item_type, заданному
источником/backend flow. Заземление идёт сразу после саммари: незаземлённые
утверждения не должны дойти до оценки.

Правки пользователя не перезаписываются (FR-043, инвариант 6): поле, у которого
есть запись в журнале с author != ai, пропускается.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.llm.contracts import ClassifyResult, ScoreResultRaw, SummarizeResult
from src.llm.prompts import (
    CLASSIFY,
    SUMMARIZE,
    build_score_prompt,
    classify_user_message,
    score_user_message,
    summarize_user_message,
)
from src.llm.provider import LLMError, LLMProvider
from src.models import (
    Act,
    ActEvent,
    ActEventType,
    ActStage,
    Assessment,
    AssessmentScheme,
    Author,
    CompanyProfile,
    Item,
    ItemType,
    Revision,
    Summary,
)
from src.pipeline.act_identifier import canonical_act_identifier
from src.pipeline.dedup import cluster_item
from src.pipeline.grounding import build_summary_text, check_entailment, check_quotes, grounding_stats
from src.scoring import ScoringError, get_scoring_config
from src.scoring import score as compute_score

logger = logging.getLogger(__name__)

SCHEME_BY_TYPE = {
    ItemType.ACT: AssessmentScheme.NPA_K1_K6,
    ItemType.NEWS: AssessmentScheme.NEWS_H1_H4,
}


@dataclass
class ProcessResult:
    item_id: int
    summarized: bool = False
    classified: bool = False
    scored: bool = False
    clustered: bool = False
    skipped_fields: list[str] = None  # type: ignore[assignment]
    grounding: dict[str, int] = None  # type: ignore[assignment]
    act_identifier: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    # Догоняющая кластеризация уже обработанных карточек — не обработка материала.
    # Пока признака не было, эти записи попадали в общий список и портили отчёт:
    # число «обработано» завышалось, а среднее время на материал занижалось,
    # потому что у них нулевая длительность. Ровно из этого получилась неверная
    # цифра SC-003 в первом прогоне корпуса.
    is_clustering_only: bool = False

    def __post_init__(self) -> None:
        self.skipped_fields = self.skipped_fields or []
        self.grounding = self.grounding or {}


async def user_edited_fields(session: AsyncSession, entity_type: str, entity_id: int) -> set[str]:
    """Поля, которые правил человек. Автоматическая переобработка их не касается."""
    stmt = select(Revision.field).where(
        Revision.entity_type == entity_type,
        Revision.entity_id == entity_id,
        Revision.author != Author.AI,
    )
    return set((await session.execute(stmt)).scalars().all())


async def get_active_profile(session: AsyncSession) -> CompanyProfile:
    profile = (
        await session.execute(select(CompanyProfile).where(CompanyProfile.is_active.is_(True)))
    ).scalar_one_or_none()
    if profile is None:
        # Без профиля оценка релевантности не имеет смысла: ценность материала
        # определяется эффектом для конкретной компании (принцип I).
        raise RuntimeError(
            "Активный профиль компании не задан. Выполните: python -m src.cli seed-profiles"
        )
    return profile


async def process_item(
    session: AsyncSession,
    item: Item,
    provider: LLMProvider,
    profile: CompanyProfile | None = None,
) -> ProcessResult:
    """Обрабатывает один материал. Ошибка на любом шаге не теряет материал."""
    started = datetime.now(UTC)
    result = ProcessResult(item_id=item.id)
    active_profile = profile or await get_active_profile(session)

    # Связи грузим явно: материал мог прийти любым путём, а ленивая подгрузка
    # в асинхронном контексте падает с MissingGreenlet.
    await session.refresh(item, ["source", "summaries", "assessments", "story"])

    edited_item = await user_edited_fields(session, "item", item.id)
    edited_summary = await user_edited_fields(session, "summary", item.id)

    # --- 1. Саммари и заземление ---
    if "summary" in edited_summary or "text" in edited_summary:
        result.skipped_fields.append("summary")
        logger.info("Item %s: саммари правил человек — пропускаю", item.id)
    else:
        try:
            raw_summary = await provider.complete_json(
                SUMMARIZE.id,
                SUMMARIZE.system,
                summarize_user_message(item.title, item.raw_text, item.source.title),
                SummarizeResult,
            )
            claims = check_quotes(raw_summary.claims, item.raw_text)
            claims = await check_entailment(claims, provider)
            result.grounding = grounding_stats(claims)

            await _replace_summary(
                session,
                item,
                text=build_summary_text(claims),
                claims=claims,
                entities=raw_summary.entities.model_dump(),
                model=provider.model,
                prompt_version=SUMMARIZE.id,
            )
            result.summarized = True
        except LLMError as exc:
            result.error = f"саммаризация: {exc}"
            logger.warning("Item %s: %s", item.id, result.error)

    summary_text = item.current_summary.text if item.current_summary else item.title

    # --- 2. Классификация ---
    if "topic" in edited_item:
        result.skipped_fields.append("classification")
    else:
        try:
            classified = await provider.complete_json(
                CLASSIFY.id,
                CLASSIFY.system,
                classify_user_message(
                    item.title,
                    summary_text or item.raw_text,
                    item.url,
                    str(item.item_type),
                ),
                ClassifyResult,
            )
            item.topic = classified.topic
            result.act_identifier = await _link_or_create_act(
                session, item, classified.act_identifier
            )
            result.classified = True
        except LLMError as exc:
            result.error = f"классификация: {exc}"
            logger.warning("Item %s: %s", item.id, result.error)

    # --- 3. Оценка влияния ---
    if "assessment" in edited_item or "scores" in await user_edited_fields(
        session, "assessment", item.id
    ):
        result.skipped_fields.append("assessment")
    else:
        scored = await _score_item(session, item, provider, active_profile, summary_text)
        result.scored = scored
        if not scored:
            item.assessment_failed = True

    # --- 4. Кластеризация дублей ---
    # Только после саммари: гейт по сущностям и факт из карточки уже есть.
    try:
        if item.item_type == ItemType.NEWS:
            story = await cluster_item(session, item, provider)
            result.clustered = story is not None and story.item_count > 1
    except Exception:
        logger.exception("Item %s: кластеризация провалилась", item.id)

    item.processed_at = datetime.now(UTC)
    await session.flush()

    result.duration_seconds = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "Item %s обработан за %.1f с (саммари=%s, класс=%s, оценка=%s)",
        item.id,
        result.duration_seconds,
        result.summarized,
        result.classified,
        result.scored,
    )
    return result


async def _link_or_create_act(
    session: AsyncSession,
    item: Item,
    act_identifier: str | None,
) -> str | None:
    """Связывает НПА-материал с досье; полный lifecycle стадий остаётся T061-T065."""
    if item.item_type != ItemType.ACT:
        return act_identifier
    identifier = canonical_act_identifier(act_identifier, item.url)
    item.act_identifier = identifier
    if not identifier or item.act_id is not None:
        return identifier
    act = (
        await session.execute(select(Act).where(Act.act_identifier == identifier))
    ).scalar_one_or_none()
    if act is None:
        act = Act(
            act_identifier=identifier,
            doc_type="НПА",
            stage=ActStage.ANNOUNCEMENT,
            source_url=item.url,
            essence=item.current_summary.text if item.current_summary else item.title,
            is_tracked=False,
        )
        session.add(act)
        await session.flush()
        session.add(
            ActEvent(
                act_id=act.id,
                event_type=ActEventType.OTHER,
                occurred_at=item.published_at.date(),
                description="Досье создано из входящего материала.",
                source_item_id=item.id,
                document_url=item.url,
            )
        )
    item.act_id = act.id
    item.act = act
    return identifier


async def _score_item(
    session: AsyncSession,
    item: Item,
    provider: LLMProvider,
    profile: CompanyProfile,
    summary_text: str,
) -> bool:
    config = get_scoring_config()
    scheme = SCHEME_BY_TYPE[item.item_type]
    prompt = build_score_prompt(
        scheme, config, profile.as_prompt_context(), datetime.now(UTC).date()
    )

    try:
        raw = await provider.complete_json(
            prompt.id,
            prompt.system,
            score_user_message(
                item.title, summary_text, item.raw_text, item.published_at.date().isoformat()
            ),
            ScoreResultRaw,
        )
    except LLMError as exc:
        logger.warning("Item %s: оценка не получена — %s", item.id, str(exc)[:200])
        return False

    try:
        # Здесь модель заканчивается и начинается детерминированная часть:
        # индекс, категорию и флаги считает код (принцип II).
        computed = compute_score(
            raw.scores, scheme, raw.escalation_candidates, config=config
        )
    except ScoringError as exc:
        logger.warning("Item %s: баллы не прошли валидацию — %s", item.id, exc)
        return False

    await _replace_assessment(
        session,
        item=item,
        profile=profile,
        computed=computed,
        rationales=raw.rationales,
        model=provider.model,
        prompt_version=prompt.id,
    )
    item.is_relevant = computed.is_relevant
    item.assessment_failed = False
    return True


async def _replace_summary(
    session: AsyncSession,
    item: Item,
    *,
    text: str,
    claims: list[dict],
    entities: dict,
    model: str,
    prompt_version: str,
) -> None:
    """Новая версия саммари. Прежняя не удаляется — инвариант 1 и FR-042.

    Это осознанное отличие от драфта news_parser, где топики удалялись при каждом
    пересчёте: там правка пользователя исчезала через час, а идентификаторы менялись.
    """
    # Снимаем признак текущей одним запросом: коллекцию для этого загружать незачем,
    # а на большой истории версий перебор в Python — лишняя работа.
    await session.execute(
        update(Summary)
        .where(Summary.item_id == item.id, Summary.is_current.is_(True))
        .values(is_current=False)
    )

    session.add(
        Summary(
            item_id=item.id,
            text=text,
            claims=claims,
            entities=entities,
            author=Author.AI,
            model=model,
            prompt_version=prompt_version,
            is_current=True,
        )
    )
    await session.flush()
    await session.refresh(item, ["summaries"])


async def _replace_assessment(
    session: AsyncSession,
    *,
    item: Item,
    profile: CompanyProfile,
    computed,
    rationales: dict[str, str],
    model: str,
    prompt_version: str,
) -> None:
    await session.execute(
        update(Assessment)
        .where(Assessment.item_id == item.id, Assessment.is_current.is_(True))
        .values(is_current=False)
    )

    session.add(
        Assessment(
            item_id=item.id,
            profile_id=profile.id,
            scheme=computed.scheme,
            scores=computed.scores,
            rationales=rationales,
            index_value=computed.index_value,
            category=computed.category,
            escalation_flags=computed.escalation_flags,
            final_category=computed.final_category,
            author=Author.AI,
            model=model,
            prompt_version=prompt_version,
            is_current=True,
        )
    )
    # Досье наследует оценку привязанного материала — задача T062, FR-035.
    # Влияние законопроекта и есть влияние того, о чём написан материал. Без
    # этого досье оставалось с пустой категорией и пустым графиком динамики,
    # хотя все связанные материалы оценены: оценки писались только на item_id,
    # а карточка досье читает собственные assessments по act_id.
    # Каждая новая публикация или смена стадии добавляет точку в историю,
    # прежняя оценка сохраняется — из неё и строится динамика влияния.
    if item.act_id is not None:
        await session.execute(
            update(Assessment)
            .where(Assessment.act_id == item.act_id, Assessment.is_current.is_(True))
            .values(is_current=False)
        )
        session.add(
            Assessment(
                act_id=item.act_id,
                profile_id=profile.id,
                scheme=computed.scheme,
                scores=computed.scores,
                rationales=rationales,
                index_value=computed.index_value,
                category=computed.category,
                escalation_flags=computed.escalation_flags,
                final_category=computed.final_category,
                author=Author.AI,
                model=model,
                prompt_version=prompt_version,
                is_current=True,
            )
        )

    await session.flush()
    await session.refresh(item, ["assessments"])


async def process_unprocessed(
    session: AsyncSession, provider: LLMProvider, limit: int = 20
) -> list[ProcessResult]:
    """Обрабатывает новые материалы и догоняет кластеризацию уже размеченных."""
    profile = await get_active_profile(session)
    stmt = (
        select(Item)
        .where(Item.processed_at.is_(None))
        .order_by(Item.published_at.desc())
        .limit(limit)
        .options(
            selectinload(Item.source),
            selectinload(Item.summaries),
            selectinload(Item.assessments),
            selectinload(Item.story),
        )
    )
    items = list((await session.execute(stmt)).scalars().all())

    results: list[ProcessResult] = []
    for item in items:
        # Идентификатор снимаем заранее: rollback сбрасывает состояние объекта,
        # и обращение к item.id внутри обработчика ошибки лезет в базу. В асинхронном
        # контексте это падает с MissingGreenlet — обработчик сам роняет прогон,
        # а настоящая причина сбоя теряется. Так один заблокированный файл базы
        # оборвал переобработку корпуса на 49-м материале из 184.
        item_id = item.id
        try:
            results.append(await process_item(session, item, provider, profile))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("Item %s: обработка провалилась", item_id)
            results.append(ProcessResult(item_id=item_id, error=str(exc)[:300]))

    # Даже при полной очереди обработки оставляем слоты на кластеризацию
    # уже размеченных карточек — иначе US6 на живой базе не стартует.
    leftover = max(limit - len(items), min(5, limit))
    if leftover:
        pending = list(
            (
                await session.execute(
                    select(Item)
                    .where(
                        Item.processed_at.isnot(None),
                        Item.item_type == ItemType.NEWS,
                        Item.story_id.is_(None),
                        Item.is_hidden.is_(False),
                    )
                    .order_by(Item.published_at.desc())
                    .limit(leftover)
                    .options(
                        selectinload(Item.source),
                        selectinload(Item.summaries),
                        selectinload(Item.story),
                    )
                )
            )
            .scalars()
            .all()
        )
        for item in pending:
            item_id = item.id  # см. выше: после rollback обращение к item.id падает
            try:
                story = await cluster_item(session, item, provider)
                await session.commit()
                results.append(
                    ProcessResult(
                        item_id=item_id,
                        clustered=story is not None and story.item_count > 1,
                        is_clustering_only=True,
                    )
                )
            except Exception as exc:
                await session.rollback()
                logger.exception("Item %s: догоняющая кластеризация провалилась", item_id)
                results.append(
                    ProcessResult(item_id=item_id, error=str(exc)[:300], is_clustering_only=True)
                )
    return results
