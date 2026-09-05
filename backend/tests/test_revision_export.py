from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.evals.revisions import export_revisions
from src.models import Author, Item, Revision


@pytest.mark.asyncio
async def test_revision_export_keeps_machine_baseline_for_repeated_edits(
    session: AsyncSession, item: Item, tmp_path: Path
) -> None:
    session.add_all(
        [
            Revision(
                entity_type="item",
                entity_id=item.id,
                field="title",
                old_value="Машинный заголовок",
                new_value="Первая правка",
                author=Author.HUMAN,
            ),
            Revision(
                entity_type="item",
                entity_id=item.id,
                field="title",
                old_value="Первая правка",
                new_value="Итоговый заголовок",
                author=Author.HUMAN,
            ),
        ]
    )
    await session.commit()
    output = tmp_path / "evals" / "revisions.jsonl"

    count = await export_revisions(session, output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    assert count == 2
    assert [row["baseline_value"] for row in rows] == [
        "Машинный заголовок",
        "Машинный заголовок",
    ]
    assert rows[-1]["target_value"] == "Итоговый заголовок"
    assert rows[-1]["item"]["url"] == item.url
    assert rows[-1]["edited_at"]
