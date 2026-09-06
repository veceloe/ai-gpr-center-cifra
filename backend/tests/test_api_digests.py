"""Дайджест и управление досье — FR-032…FR-037, FR-070…FR-072."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.main import app
from src.db import get_db
from src.models import Act, ActStage, Author, CompanyProfile, Item, ItemType, Revision, Source, Summary


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def items(session: AsyncSession, source: Source, profile: CompanyProfile) -> list[Item]:
    created = []
    for n, title in enumerate(
        ["Требования к реестру ПО", "Закон о технологиях ИИ", "Штрафы операторам"], start=1
    ):
        item = Item(
            source_id=source.id,
            url=f"https://example.test/d/{n}",
            title=title,
            raw_text=f"Текст материала {n}",
            content_hash=f"dh-{n}",
            published_at=datetime(2026, 9, n, tzinfo=UTC),
            item_type=ItemType.ACT,
            act_identifier=f"Законопроект № {1000000 + n}-8",
            is_relevant=True,
            tags=[],
        )
        session.add(item)
        await session.flush()
        session.add(
            Summary(item_id=item.id, text=f"Саммари {n}.", claims=[], entities={},
                    author=Author.AI, is_current=True)
        )
        created.append(item)
    await session.commit()
    return created


class TestDigest:
    @pytest.mark.asyncio
    async def test_created_in_selection_order(self, client: AsyncClient, items: list[Item]) -> None:
        """Порядок отбора сохраняется: пользователь уже прошёл ленту по влиянию."""
        ids = [items[2].id, items[0].id, items[1].id]
        response = await client.post(
            "/digests", json={"recipient": "Директор по развитию", "item_ids": ids}
        )
        assert response.status_code == 201
        body = response.json()
        assert [e["item"]["id"] for e in body["entries"]] == ids
        assert body["recipient"] == "Директор по развитию"
        assert body["title"].startswith("Дайджест за")

    @pytest.mark.asyncio
    async def test_unknown_item_rejected(self, client: AsyncClient, items: list[Item]) -> None:
        response = await client.post("/digests", json={"recipient": "X", "item_ids": [999]})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_selection_rejected(self, client: AsyncClient) -> None:
        assert (await client.post("/digests", json={"recipient": "X", "item_ids": []})).status_code == 422

    @pytest.mark.asyncio
    async def test_exclusion_is_local_to_digest(self, client: AsyncClient, items: list[Item]) -> None:
        """FR-071: исключение из дайджеста не убирает материал из ленты."""
        digest = (
            await client.post("/digests", json={"recipient": "Р", "item_ids": [i.id for i in items]})
        ).json()

        patched = await client.patch(
            f"/digests/{digest['id']}/items/{items[1].id}", json={"is_excluded": True}
        )
        assert patched.status_code == 200
        excluded = [e for e in patched.json()["entries"] if e["is_excluded"]]
        assert len(excluded) == 1

        feed = (await client.get("/feed")).json()
        assert any(i["id"] == items[1].id for i in feed["items"]), "материал пропал из ленты"

    @pytest.mark.asyncio
    async def test_export_html_omits_excluded_and_keeps_links(
        self, client: AsyncClient, items: list[Item]
    ) -> None:
        digest = (
            await client.post("/digests", json={"recipient": "Р", "item_ids": [i.id for i in items]})
        ).json()
        await client.patch(f"/digests/{digest['id']}/items/{items[1].id}", json={"is_excluded": True})

        export = await client.get(f"/digests/{digest['id']}/export", params={"format": "html"})
        assert export.status_code == 200
        text = export.text
        assert items[0].title in text
        assert items[1].title not in text, "исключённый материал попал в выгрузку"
        assert items[0].url in text, "потеряна ссылка на оригинал"

    @pytest.mark.asyncio
    async def test_export_markdown(self, client: AsyncClient, items: list[Item]) -> None:
        digest = (
            await client.post("/digests", json={"recipient": "Р", "item_ids": [items[0].id]})
        ).json()
        export = await client.get(f"/digests/{digest['id']}/export", params={"format": "md"})
        assert export.status_code == 200
        assert export.text.startswith("# ")
        assert f"]({items[0].url})" in export.text


class TestActManagement:
    @pytest_asyncio.fixture
    async def act(self, session: AsyncSession, items: list[Item]) -> Act:
        obj = Act(
            act_identifier="Законопроект № 1215252-8",
            doc_type="Законопроект",
            stage=ActStage.SUBMITTED,
            source_url="https://sozd.duma.gov.ru/bill/1215252-8",
            essence="Переход на реестровые системы условного доступа.",
            is_tracked=True,
        )
        session.add(obj)
        await session.commit()
        return obj

    @pytest.mark.asyncio
    async def test_stage_change_adds_timeline_event(self, client: AsyncClient, act: Act) -> None:
        """FR-032, FR-033: смена стадии порождает событие хронологии."""
        response = await client.patch(f"/acts/{act.id}", json={"stage": "readings"})
        assert response.status_code == 200
        body = response.json()

        assert body["stage"] == "readings"
        events = [e for e in body["timeline"] if e["event_type"] == "stage_change"]
        assert len(events) == 1
        assert "внесён" in events[0]["description"] and "чтениях" in events[0]["description"]

    @pytest.mark.asyncio
    async def test_stage_change_marks_linked_items_for_reassessment(
        self, client: AsyncClient, session: AsyncSession, act: Act, items: list[Item]
    ) -> None:
        """FR-034: после смены стадии влияние пересчитывается."""
        await client.post(f"/acts/{act.id}/link-item", json={"item_id": items[0].id})
        items[0].processed_at = datetime.now(UTC)
        await session.commit()

        await client.patch(f"/acts/{act.id}", json={"stage": "adopted"})
        refreshed = (await session.execute(select(Item).where(Item.id == items[0].id))).scalar_one()
        await session.refresh(refreshed)
        assert refreshed.processed_at is None

    @pytest.mark.asyncio
    async def test_stage_change_is_logged_as_revision(
        self, client: AsyncClient, session: AsyncSession, act: Act
    ) -> None:
        await client.patch(f"/acts/{act.id}", json={"stage": "adopted"})
        rows = (
            await session.execute(select(Revision).where(Revision.entity_type == "act"))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].old_value == "submitted" and rows[0].new_value == "adopted"

    @pytest.mark.asyncio
    async def test_same_stage_creates_no_event(self, client: AsyncClient, act: Act) -> None:
        body = (await client.patch(f"/acts/{act.id}", json={"stage": "submitted"})).json()
        assert [e for e in body["timeline"] if e["event_type"] == "stage_change"] == []

    @pytest.mark.asyncio
    async def test_unknown_stage_rejected(self, client: AsyncClient, act: Act) -> None:
        assert (await client.patch(f"/acts/{act.id}", json={"stage": "выдумка"})).status_code == 422

    @pytest.mark.asyncio
    async def test_archive_keeps_timeline(self, client: AsyncClient, act: Act) -> None:
        """FR-037: архивация сохраняет хронологию и историю оценок."""
        await client.patch(f"/acts/{act.id}", json={"stage": "in_force"})
        body = (await client.patch(f"/acts/{act.id}", json={"is_archived": True})).json()
        assert body["is_archived"] is True
        assert len(body["timeline"]) >= 1

    @pytest.mark.asyncio
    async def test_manual_event_added(self, client: AsyncClient, act: Act) -> None:
        response = await client.post(
            f"/acts/{act.id}/events",
            json={
                "event_type": "feedback",
                "occurred_at": "2026-09-10",
                "description": "Ассоциация направила отрицательный отзыв.",
                "document_url": "https://example.test/feedback.pdf",
            },
        )
        assert response.status_code == 201
        events = response.json()["timeline"]
        assert any(e["event_type"] == "feedback" and e["document_url"] for e in events)

    @pytest.mark.asyncio
    async def test_link_item_appears_in_dossier(
        self, client: AsyncClient, act: Act, items: list[Item]
    ) -> None:
        """FR-036: материал связывается с существующим досье."""
        body = (
            await client.post(f"/acts/{act.id}/link-item", json={"item_id": items[0].id})
        ).json()
        assert any(i["id"] == items[0].id for i in body["linked_items"])
        assert any(e["source_item_id"] == items[0].id for e in body["timeline"])

    @pytest.mark.asyncio
    async def test_link_is_idempotent(self, client: AsyncClient, act: Act, items: list[Item]) -> None:
        await client.post(f"/acts/{act.id}/link-item", json={"item_id": items[0].id})
        body = (
            await client.post(f"/acts/{act.id}/link-item", json={"item_id": items[0].id})
        ).json()
        assert len([e for e in body["timeline"] if e["source_item_id"] == items[0].id]) == 1
