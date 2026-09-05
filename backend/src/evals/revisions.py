"""Выгрузка пользовательских правок как эталонных меток — FR-081."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Item, Revision


async def export_revisions(session: AsyncSession, output: Path) -> int:
    revisions = list(
        (
            await session.execute(
                select(Revision).order_by(Revision.created_at, Revision.id)
            )
        )
        .scalars()
        .all()
    )
    item_ids = {revision.entity_id for revision in revisions}
    items = {
        item.id: item
        for item in (
            await session.execute(select(Item).where(Item.id.in_(item_ids)))
        ).scalars()
    }

    # Первая правка поля хранит исходное машинное значение. Для последующих
    # правок сохраняем тот же baseline, чтобы eval не сравнивал человека с человеком.
    baselines: dict[tuple[str, int, str], object] = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for revision in revisions:
            key = (revision.entity_type, revision.entity_id, revision.field)
            baseline = baselines.setdefault(key, revision.old_value)
            item = items.get(revision.entity_id)
            row = {
                "revision_id": revision.id,
                "item_id": revision.entity_id,
                "entity_type": revision.entity_type,
                "field": revision.field,
                "baseline_value": baseline,
                "old_value": revision.old_value,
                "target_value": revision.new_value,
                "author": str(revision.author),
                "reason": revision.reason,
                "edited_at": revision.created_at.isoformat(),
                "item": (
                    {
                        "title": item.title,
                        "url": item.url,
                        "item_type": str(item.item_type),
                    }
                    if item
                    else None
                ),
            }
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(revisions)
