"""Схемы ответов API — specs/001-ai-monitoring-center/contracts/api.openapi.yaml.

Контракт зафиксирован до кода и служит границей между дорожками инженеров:
менять форму ответа можно только правкой контракта, а не здесь в одностороннем порядке.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from src.models import Assessment as AssessmentModel
from src.models import Item, Revision, Source, Story, Summary


class HealthResponse(BaseModel):
    status: str = "ok"


class ClaimOut(BaseModel):
    """Заземление утверждения — FR-025."""

    statement: str
    quote: str
    char_start: int | None = None
    char_end: int | None = None
    quote_found: bool
    entailed: bool | None = None
    reject_reason: str | None = None


class EntitiesOut(BaseModel):
    who: list[str] = Field(default_factory=list)
    what: str = ""
    when: str = ""
    consequences: str = ""


class CriterionScoreOut(BaseModel):
    """Один критерий в разложении оценки — FR-024."""

    code: str
    name: str
    score: int
    max_score: int
    weight: float
    contribution: float
    scale_label: str
    rationale: str = ""


class AssessmentOut(BaseModel):
    scheme: str
    scores: dict[str, int]
    rationales: dict[str, str]
    breakdown: list[CriterionScoreOut] = Field(default_factory=list)
    index_value: float
    category: str
    escalation_flags: list[str] = Field(default_factory=list)
    final_category: str
    escalated: bool = False
    author: str
    model: str | None = None
    prompt_version: str | None = None
    created_at: datetime


class SourceRefOut(BaseModel):
    id: int
    title: str
    type: str
    category: str


class GroundingOut(BaseModel):
    """Счётчик неподтверждённого — иначе молчаливое отбрасывание рождает недоверие."""

    total: int
    accepted: int
    rejected: int


class ItemCardOut(BaseModel):
    id: int
    title: str
    summary: str
    entities: EntitiesOut
    item_type: str
    topic: str | None = None
    index_value: float | None = None
    final_category: str | None = None
    escalation_flags: list[str] = Field(default_factory=list)
    url: str
    source: SourceRefOut
    published_at: datetime
    published_at_is_approx: bool
    is_partial_text: bool
    is_relevant: bool | None = None
    is_hidden: bool
    is_edited: bool
    assessment_failed: bool
    grounding: GroundingOut | None = None
    story_id: int | None = None
    story: StoryRefOut | None = None
    act_id: int | None = None
    tags: list[str] = Field(default_factory=list)


class StoryRefOut(BaseModel):
    id: int
    item_count: int


class StoryMemberOut(BaseModel):
    id: int
    title: str
    url: str
    source: SourceRefOut
    published_at: datetime


class StoryOut(BaseModel):
    id: int
    canonical_title: str
    fact_summary: str
    first_seen_at: datetime
    item_count: int
    was_split_by_user: bool
    items: list[StoryMemberOut] = Field(default_factory=list)


class RevisionOut(BaseModel):
    field: str
    old_value: object | None = None
    new_value: object | None = None
    author: str
    reason: str | None = None
    created_at: datetime


class ItemDetailOut(ItemCardOut):
    raw_text: str
    claims: list[ClaimOut] = Field(default_factory=list)
    assessment: AssessmentOut | None = None
    user_note: str | None = None
    revisions: list[RevisionOut] = Field(default_factory=list)
    machine_summary: str | None = None
    machine_assessment: AssessmentOut | None = None


class FeedResponse(BaseModel):
    items: list[ItemCardOut]
    total: int


class SourceOut(BaseModel):
    id: int
    type: str
    category: str
    item_type: str
    url: str
    title: str
    is_active: bool
    poll_interval_min: int
    last_polled_at: datetime | None = None
    last_error: str | None = None
    item_count: int = 0


class SourceCreate(BaseModel):
    type: str
    url: str
    title: str | None = None
    category: str | None = None
    item_type: str | None = None


class SourceUpdate(BaseModel):
    title: str | None = None
    is_active: bool | None = None
    poll_interval_min: int | None = None


class ItemCreate(BaseModel):
    """Ручное добавление материала — FR-009."""

    title: str
    raw_text: str
    url: str | None = None
    published_at: datetime | None = None


class ItemPatch(BaseModel):
    """Правка полей материала — FR-040, FR-044."""

    title: str | None = None
    summary: str | None = None
    topic: str | None = None
    tags: list[str] | None = None
    user_note: str | None = None


class AssessmentPatch(BaseModel):
    """Правка баллов с немедленным пересчётом индекса — FR-041."""

    scores: dict[str, int]
    escalation_flags: list[str] | None = None


class HideRequest(BaseModel):
    hidden: bool = True
    # Причина обязательна по смыслу: клик без причины бесполезен для тюнинга порогов.
    reason: str | None = None


class ProfileOut(BaseModel):
    id: int
    slug: str
    name: str
    industry: str
    products: list[str]
    regimes: list[str]
    risk_areas: list[str]
    growth_areas: list[str]
    competitors: list[str]
    noise_markers: list[str]
    is_active: bool


class ActEventOut(BaseModel):
    event_type: str
    occurred_at: date
    description: str
    version_label: str | None = None
    document_url: str | None = None
    source_item_id: int | None = None


class ActCardOut(BaseModel):
    id: int
    act_identifier: str
    doc_type: str
    stage: str
    index_value: float | None = None
    final_category: str | None = None
    is_tracked: bool
    is_archived: bool
    effective_from: date | None = None


class ActDetailOut(ActCardOut):
    essence: str
    source_url: str
    timeline: list[ActEventOut] = Field(default_factory=list)
    assessment_history: list[AssessmentOut] = Field(default_factory=list)
    linked_items: list[ItemCardOut] = Field(default_factory=list)


# --------------------------------------------------------------------- сборка ответов


def source_ref(source: Source) -> SourceRefOut:
    return SourceRefOut(
        id=source.id, title=source.title, type=str(source.type), category=str(source.category)
    )


def assessment_out(assessment: AssessmentModel) -> AssessmentOut:
    """Разложение оценки по критериям — FR-024.

    Пользователь видит не только индекс, но и вклад каждого критерия: это то, что
    отличает объяснимую оценку от непрозрачного индекса, за который рынок критикует
    существующие системы мониторинга.
    """
    from src.scoring import get_scoring_config

    scheme_cfg = get_scoring_config().for_scheme(assessment.scheme)
    breakdown = [
        CriterionScoreOut(
            code=criterion.code,
            name=criterion.name,
            score=assessment.scores.get(criterion.code, 0),
            max_score=max(criterion.scale),
            weight=criterion.weight,
            contribution=round(assessment.scores.get(criterion.code, 0) * criterion.weight, 4),
            scale_label=criterion.scale.get(assessment.scores.get(criterion.code, 0), ""),
            rationale=assessment.rationales.get(criterion.code, ""),
        )
        for criterion in scheme_cfg.criteria
    ]

    return AssessmentOut(
        scheme=str(assessment.scheme),
        scores=assessment.scores,
        rationales=assessment.rationales,
        breakdown=breakdown,
        index_value=assessment.index_value,
        category=assessment.category,
        escalation_flags=assessment.escalation_flags,
        final_category=assessment.final_category,
        escalated=assessment.category != assessment.final_category,
        author=str(assessment.author),
        model=assessment.model,
        prompt_version=assessment.prompt_version,
        created_at=assessment.created_at,
    )


def _grounding(summary: Summary | None) -> GroundingOut | None:
    if summary is None:
        return None
    return GroundingOut(
        total=len(summary.claims),
        accepted=len(summary.accepted_claims),
        rejected=len(summary.rejected_claims),
    )


def item_card(item: Item, *, is_edited: bool = False) -> ItemCardOut:
    summary = item.current_summary
    assessment = item.current_assessment
    return ItemCardOut(
        id=item.id,
        title=item.title,
        summary=summary.text if summary else "",
        entities=EntitiesOut(**(summary.entities if summary else {})),
        item_type=str(item.item_type),
        topic=str(item.topic) if item.topic else None,
        index_value=assessment.index_value if assessment else None,
        final_category=assessment.final_category if assessment else None,
        escalation_flags=assessment.escalation_flags if assessment else [],
        url=item.url,
        source=source_ref(item.source),
        published_at=item.published_at,
        published_at_is_approx=item.published_at_is_approx,
        is_partial_text=item.is_partial_text,
        is_relevant=item.is_relevant,
        is_hidden=item.is_hidden,
        is_edited=is_edited,
        assessment_failed=item.assessment_failed,
        grounding=_grounding(summary),
        story_id=item.story_id,
        story=_story_ref(item),
        act_id=item.act_id,
        tags=item.tags or [],
    )


def _story_ref(item: Item) -> StoryRefOut | None:
    if item.story_id is None:
        return None
    count = item.story.item_count if item.story is not None else 0
    if item.story is not None and not count:
        count = len(item.story.items)
    return StoryRefOut(id=item.story_id, item_count=count)


def story_out(story: Story) -> StoryOut:
    return StoryOut(
        id=story.id,
        canonical_title=story.canonical_title,
        fact_summary=story.fact_summary,
        first_seen_at=story.first_seen_at,
        item_count=story.item_count or len(story.items),
        was_split_by_user=story.was_split_by_user,
        items=[
            StoryMemberOut(
                id=member.id,
                title=member.title,
                url=member.url,
                source=source_ref(member.source),
                published_at=member.published_at,
            )
            for member in story.items
        ],
    )


def item_detail(
    item: Item,
    *,
    is_edited: bool = False,
    revisions: list[Revision] | None = None,
) -> ItemDetailOut:
    summary = item.current_summary
    assessment = item.current_assessment
    machine_summaries = [version for version in item.summaries if str(version.author) == "ai"]
    machine_assessments = [
        version for version in item.assessments if str(version.author) == "ai"
    ]
    machine_summary = machine_summaries[-1] if machine_summaries else None
    machine_assessment = machine_assessments[-1] if machine_assessments else None
    card = item_card(item, is_edited=is_edited)
    return ItemDetailOut(
        **card.model_dump(),
        raw_text=item.raw_text,
        claims=[ClaimOut(**claim) for claim in (summary.claims if summary else [])],
        assessment=assessment_out(assessment) if assessment else None,
        user_note=item.user_note,
        revisions=[
            RevisionOut(
                field=revision.field,
                old_value=revision.old_value,
                new_value=revision.new_value,
                author=str(revision.author),
                reason=revision.reason,
                created_at=revision.created_at,
            )
            for revision in (revisions or [])
        ],
        machine_summary=machine_summary.text if machine_summary else None,
        machine_assessment=assessment_out(machine_assessment) if machine_assessment else None,
    )
