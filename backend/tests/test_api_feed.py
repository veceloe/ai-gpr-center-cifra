"""Лента и карточка через HTTP — FR-020…FR-025, FR-040…FR-045.

Тесты идут через реальное приложение с подменённой зависимостью базы: проверяется
контракт, который увидит фронтенд, а не внутренние вызовы.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.main import app
from src.db import get_db
from src.models import (
    Assessment,
    AssessmentScheme,
    Author,
    CompanyProfile,
    Item,
    ItemType,
    Source,
    Story,
    Summary,
)


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def scored_items(session: AsyncSession, source: Source, profile: CompanyProfile) -> list[Item]:
    """Три материала с разным индексом: проверяем порядок и фильтры."""
    created: list[Item] = []
    for n, (title, index, category, text) in enumerate(
        [
            ("Требования к реестру российского ПО", 78.3, "Высокое", "Постановление о доверенных ОС"),
            ("Закон о поддержке технологий ИИ", 51.7, "Среднее", "Маркировка контента с марта"),
            ("Новости агрономии", 8.3, "Незначительное", "Урожай кукурузы вырос"),
        ],
        start=1,
    ):
        item = Item(
            source_id=source.id,
            url=f"https://example.test/a/{n}",
            title=title,
            raw_text=text,
            content_hash=f"hash-{n}",
            published_at=datetime(2026, 9, n, tzinfo=UTC),
            is_relevant=index > 25,
            tags=["регуляторика"] if index > 25 else [],
        )
        session.add(item)
        await session.flush()

        session.add(
            Summary(
                item_id=item.id,
                text=f"Саммари: {title}.",
                claims=[{"statement": title, "quote": text, "quote_found": True, "entailed": True}],
                entities={"who": ["Правительство"], "what": title, "when": "", "consequences": ""},
                author=Author.AI,
                is_current=True,
            )
        )
        session.add(
            Assessment(
                item_id=item.id,
                profile_id=profile.id,
                scheme=AssessmentScheme.NPA_K1_K6,
                scores={"К1": 3, "К2": 3, "К3": 2, "К4": 2, "К5": 1, "К6": 3},
                rationales={"К1": "прямое влияние на продукты"},
                index_value=index,
                category=category,
                escalation_flags=[],
                final_category=category,
                author=Author.AI,
                is_current=True,
            )
        )
        created.append(item)

    await session.commit()
    return created


class TestFeed:
    @pytest.mark.asyncio
    async def test_sorted_by_impact_not_by_date(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        """Специалист начинает день с самого влияющего, а не с самого свежего."""
        response = await client.get("/feed")
        assert response.status_code == 200
        body = response.json()

        indexes = [i["index_value"] for i in body["items"]]
        assert indexes == sorted(indexes, reverse=True)
        assert body["items"][0]["final_category"] == "Высокое"

    @pytest.mark.asyncio
    async def test_irrelevant_excluded_by_default(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        """Шум не попадает в основную ленту, но остаётся доступным — FR-018."""
        default = (await client.get("/feed")).json()
        assert all(i["title"] != "Новости агрономии" for i in default["items"])

        with_noise = (await client.get("/feed", params={"include_irrelevant": True})).json()
        assert any(i["title"] == "Новости агрономии" for i in with_noise["items"])

    @pytest.mark.asyncio
    async def test_card_carries_grounding_counter(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        body = (await client.get("/feed")).json()
        grounding = body["items"][0]["grounding"]
        assert grounding == {"total": 1, "accepted": 1, "rejected": 0}

    @pytest.mark.asyncio
    async def test_filter_by_category(self, client: AsyncClient, scored_items: list[Item]) -> None:
        body = (await client.get("/feed", params={"category": "Среднее"})).json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Закон о поддержке технологий ИИ"


class TestSearch:
    """Регрессия: поиск по кириллице был сломан регистром.

    Встроенная в SQLite lower() умеет только ASCII, поэтому «маркировка» не находила
    «Маркировка». Для русскоязычного корпуса это делало поиск бесполезным.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", ["маркировка", "Маркировка", "МАРКИРОВКА"])
    async def test_case_insensitive_cyrillic(
        self, client: AsyncClient, scored_items: list[Item], query: str
    ) -> None:
        body = (await client.get("/feed", params={"q": query})).json()
        assert body["total"] == 1, f"поиск по {query!r} не нашёл материал"

    @pytest.mark.asyncio
    async def test_search_covers_tags_and_entities(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        """FR-022: поиск по тексту, тегам и извлечённым сущностям."""
        by_tag = (await client.get("/feed", params={"q": "регуляторика"})).json()
        assert by_tag["total"] == 2

        by_entity = (await client.get("/feed", params={"q": "правительство"})).json()
        assert by_entity["total"] >= 1

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        body = (await client.get("/feed", params={"q": "нетакогослова"})).json()
        assert body == {"items": [], "total": 0}


class TestItemCard:
    @pytest.mark.asyncio
    async def test_detail_exposes_claims_with_offsets(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        item_id = scored_items[0].id
        body = (await client.get(f"/items/{item_id}")).json()
        assert body["claims"][0]["quote_found"] is True
        assert body["assessment"]["index_value"] == 78.3

    @pytest.mark.asyncio
    async def test_assessment_breakdown_is_explained(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        """FR-024: пользователь видит вклад каждого критерия, а не только итог."""
        body = (await client.get(f"/items/{scored_items[0].id}")).json()
        breakdown = body["assessment"]["breakdown"]

        assert [c["code"] for c in breakdown] == ["К1", "К2", "К3", "К4", "К5", "К6"]
        k1 = breakdown[0]
        assert k1["score"] == 3
        assert k1["weight"] == 0.25
        assert k1["contribution"] == 0.75
        assert k1["scale_label"]
        assert k1["rationale"] == "прямое влияние на продукты"

    @pytest.mark.asyncio
    async def test_missing_item_returns_404(self, client: AsyncClient) -> None:
        assert (await client.get("/items/9999")).status_code == 404


class TestManualEditing:
    @pytest.mark.asyncio
    async def test_score_patch_recomputes_index(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        """FR-041: правка одного балла пересчитывает индекс немедленно."""
        item_id = scored_items[0].id
        response = await client.patch(f"/items/{item_id}/assessment", json={"scores": {"К1": 0}})
        assert response.status_code == 200

        body = response.json()
        assert body["scores"]["К1"] == 0
        assert body["index_value"] == 53.3
        assert body["author"] == "human"
        detail = (await client.get(f"/items/{item_id}")).json()
        assert detail["machine_assessment"]["author"] == "ai"
        assert any(revision["field"] == "scores" for revision in detail["revisions"])

    @pytest.mark.asyncio
    async def test_bad_score_rejected_with_422(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        response = await client.patch(
            f"/items/{scored_items[0].id}/assessment", json={"scores": {"К1": 9}}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_hide_and_restore(self, client: AsyncClient, scored_items: list[Item]) -> None:
        item_id = scored_items[0].id
        hidden = await client.post(
            f"/items/{item_id}/hide", json={"hidden": True, "reason": "не наш профиль"}
        )
        assert hidden.status_code == 204

        assert all(i["id"] != item_id for i in (await client.get("/feed")).json()["items"])
        assert any(
            i["id"] == item_id
            for i in (await client.get("/feed", params={"include_hidden": True})).json()["items"]
        )

        await client.post(f"/items/{item_id}/hide", json={"hidden": False})
        assert any(i["id"] == item_id for i in (await client.get("/feed")).json()["items"])

    @pytest.mark.asyncio
    async def test_edit_fields_are_revised_and_machine_summary_is_available(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        item_id = scored_items[0].id
        machine_summary = (await client.get(f"/items/{item_id}")).json()["summary"]
        response = await client.patch(
            f"/items/{item_id}",
            json={
                "title": "Исправленный заголовок",
                "summary": "Проверенное специалистом саммари.",
                "topic": "regulatory",
                "tags": ["важно", "реестр ПО"],
                "user_note": "на совещание 15-го",
            },
        )
        assert response.status_code == 200

        body = (await client.get(f"/items/{item_id}")).json()
        assert body["is_edited"] is True
        assert body["title"] == "Исправленный заголовок"
        assert body["summary"] == "Проверенное специалистом саммари."
        assert body["tags"] == ["важно", "реестр ПО"]
        assert body["user_note"] == "на совещание 15-го"
        assert body["machine_summary"] == machine_summary
        assert {revision["field"] for revision in body["revisions"]} >= {
            "title",
            "text",
            "topic",
            "tags",
            "user_note",
        }
        assert all(revision["author"] == "human" for revision in body["revisions"])
        assert all(revision["created_at"] for revision in body["revisions"])

    @pytest.mark.asyncio
    async def test_hiding_requires_reason(
        self, client: AsyncClient, scored_items: list[Item]
    ) -> None:
        response = await client.post(
            f"/items/{scored_items[0].id}/hide",
            json={"hidden": True},
        )
        assert response.status_code == 422


class TestSourceItemType:
    @pytest.mark.asyncio
    async def test_item_type_is_stored_when_source_is_created(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        telegram = await client.post(
            "/sources",
            json={"type": "telegram", "url": "https://t.me/example_news"},
        )
        regulator = await client.post(
            "/sources",
            json={"type": "web", "url": "https://duma.example/documents"},
        )

        assert telegram.status_code == regulator.status_code == 201
        assert telegram.json()["item_type"] == ItemType.NEWS
        assert regulator.json()["item_type"] == ItemType.ACT
        stored = await session.get(Source, regulator.json()["id"])
        assert stored is not None
        assert stored.item_type == ItemType.ACT


class TestManualItemCreation:
    @pytest.mark.asyncio
    async def test_manual_item_enters_feed(self, client: AsyncClient, profile: CompanyProfile) -> None:
        """FR-009: материал, которого не было в источниках."""
        response = await client.post(
            "/items",
            json={
                "title": "Внутренний GR-дайджест",
                "raw_text": "Ассоциация направила предложения в Минцифры по срокам перехода.",
            },
        )
        assert response.status_code == 201
        created = response.json()
        assert created["published_at_is_approx"] is True

        feed = (await client.get("/feed")).json()
        assert any(i["id"] == created["id"] for i in feed["items"])

    @pytest.mark.asyncio
    async def test_empty_text_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/items", json={"title": "Пусто", "raw_text": "   "})
        assert response.status_code == 422


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_for_deploy_gate(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStoryCard:
    @pytest.mark.asyncio
    async def test_event_card_lists_original_urls_and_split_unmerges(
        self,
        client: AsyncClient,
        session: AsyncSession,
        source: Source,
        scored_items: list[Item],
    ) -> None:
        story = Story(
            canonical_title="Один факт",
            fact_summary="Повтор публикации",
            item_count=2,
        )
        session.add(story)
        await session.flush()
        scored_items[0].story_id = story.id
        scored_items[1].story_id = story.id
        await session.commit()

        card = await client.get(f"/stories/{story.id}")
        assert card.status_code == 200
        body = card.json()
        assert body["item_count"] == 2
        assert {member["url"] for member in body["items"]} == {
            scored_items[0].url,
            scored_items[1].url,
        }
        assert all(member["source"]["title"] == source.title for member in body["items"])

        feed = (await client.get("/feed")).json()
        story_rows = [item for item in feed["items"] if item.get("story")]
        assert len(story_rows) == 1
        assert story_rows[0]["story"]["item_count"] == 2

        split = await client.post(f"/stories/{story.id}/split")
        assert split.status_code == 204
        after = (await client.get(f"/stories/{story.id}")).json()
        assert after["was_split_by_user"] is True
        assert after["items"] == []
