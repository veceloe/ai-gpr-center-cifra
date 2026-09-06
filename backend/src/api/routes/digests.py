"""Дайджест под получателя — FR-070, FR-071, FR-072.

Итог мониторинга — не лента, а подготовленный материал, с которым дальше работают
другие люди. По данным исследования это ещё и главный механизм удержания:
новостные агрегаторы умирают на реактивном использовании, а обязательный рабочий
артефакт встроен в дедлайн специалиста.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import DigestCreate, DigestEntryPatch, DigestOut, digest_out
from src.db import get_db
from src.models import Digest, DigestItem, Item

router = APIRouter(tags=["digests"])


def _digest_options():
    return (
        selectinload(Digest.entries).selectinload(DigestItem.item).selectinload(Item.source),
        selectinload(Digest.entries).selectinload(DigestItem.item).selectinload(Item.summaries),
        selectinload(Digest.entries).selectinload(DigestItem.item).selectinload(Item.assessments),
        selectinload(Digest.entries).selectinload(DigestItem.item).selectinload(Item.story),
    )


async def _load(db: AsyncSession, digest_id: int) -> Digest:
    digest = (
        await db.execute(select(Digest).where(Digest.id == digest_id).options(*_digest_options()))
    ).scalar_one_or_none()
    if digest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Digest not found")
    return digest


@router.get("/digests", response_model=list[DigestOut])
async def list_digests(db: Annotated[AsyncSession, Depends(get_db)]) -> list[DigestOut]:
    digests = (
        (await db.execute(select(Digest).options(*_digest_options()).order_by(Digest.created_at.desc())))
        .unique()
        .scalars()
        .all()
    )
    return [digest_out(d) for d in digests]


@router.post("/digests", response_model=DigestOut, status_code=status.HTTP_201_CREATED)
async def create_digest(
    payload: DigestCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> DigestOut:
    if not payload.item_ids:
        raise HTTPException(status_code=422, detail="Не выбрано ни одного материала")

    found = list(
        (await db.execute(select(Item).where(Item.id.in_(payload.item_ids)))).scalars().all()
    )
    missing = set(payload.item_ids) - {i.id for i in found}
    if missing:
        raise HTTPException(status_code=422, detail=f"Материалы не найдены: {sorted(missing)}")

    title = (payload.title or "").strip() or (
        f"Дайджест за {datetime.now(UTC).strftime('%d.%m.%Y')}"
    )
    digest = Digest(recipient=payload.recipient.strip(), title=title)
    db.add(digest)
    await db.flush()

    # Порядок сохраняем тот, в котором пользователь отобрал материалы: он уже
    # прошёл ленту, отсортированную по влиянию, и его отбор — осознанный.
    for position, item_id in enumerate(payload.item_ids):
        db.add(DigestItem(digest_id=digest.id, item_id=item_id, position=position))

    await db.commit()
    return digest_out(await _load(db, digest.id))


@router.get("/digests/{digest_id}", response_model=DigestOut)
async def get_digest(digest_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> DigestOut:
    return digest_out(await _load(db, digest_id))


@router.patch("/digests/{digest_id}/items/{item_id}", response_model=DigestOut)
async def toggle_entry(
    digest_id: int,
    item_id: int,
    payload: DigestEntryPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DigestOut:
    """Исключение материала из дайджеста не удаляет его из ленты — FR-071.

    Один и тот же материал бывает полезен одному получателю и лишний другому,
    поэтому исключение локально для конкретного дайджеста.
    """
    digest = await _load(db, digest_id)
    entry = next((e for e in digest.entries if e.item_id == item_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Материала нет в этом дайджесте")

    entry.is_excluded = payload.is_excluded
    await db.commit()
    return digest_out(await _load(db, digest_id))


@router.delete("/digests/{digest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_digest(digest_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    digest = await _load(db, digest_id)
    await db.delete(digest)
    await db.commit()


@router.get("/digests/{digest_id}/export", response_class=PlainTextResponse)
async def export_digest(
    digest_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    format: Annotated[str, Query(pattern="^(html|md)$")] = "html",
) -> PlainTextResponse:
    """Выгрузка для отправки по почте — FR-072.

    Ссылка на оригинал сохраняется у каждого материала: получатель должен иметь
    возможность проверить первоисточник, а не верить пересказу.
    """
    digest = await _load(db, digest_id)
    included = [e for e in digest.entries if not e.is_excluded]
    generated = datetime.now(UTC).strftime("%d.%m.%Y")

    if format == "md":
        lines = [f"# {digest.title}", "", f"Получатель: {digest.recipient}  ", f"Дата: {generated}", ""]
        for entry in included:
            item = entry.item
            assessment = item.current_assessment
            summary = item.current_summary
            mark = f" — {assessment.final_category} ({assessment.index_value:.1f})" if assessment else ""
            lines.append(f"## {item.title}{mark}")
            lines.append("")
            if summary and summary.text:
                lines.append(summary.text)
                lines.append("")
            lines.append(f"Источник: {item.source.title} · [оригинал]({item.url})")
            if item.user_note:
                lines.append(f"\n> Пометка: {item.user_note}")
            lines.append("")
        body = "\n".join(lines)
        return PlainTextResponse(body, media_type="text/markdown; charset=utf-8")

    blocks = []
    for entry in included:
        item = entry.item
        assessment = item.current_assessment
        summary = item.current_summary
        badge = ""
        if assessment:
            badge = (
                f'<span style="font-size:12px;color:#5b667a">'
                f"{html.escape(assessment.final_category)} · {assessment.index_value:.1f}</span>"
            )
        note = (
            f'<p style="margin:8px 0 0;padding:8px 12px;background:#f4f6fa;'
            f'border-radius:4px;font-size:14px">Пометка: {html.escape(item.user_note)}</p>'
            if item.user_note
            else ""
        )
        blocks.append(
            f"""<article style="margin:0 0 28px;padding:0 0 22px;border-bottom:1px solid #e2e7f0">
  <h2 style="margin:0 0 6px;font-size:17px;line-height:1.3;color:#0e1428">{html.escape(item.title)}</h2>
  {badge}
  <p style="margin:10px 0 0;font-size:15px;line-height:1.5;color:#26313f">
    {html.escape(summary.text) if summary and summary.text else ""}</p>
  {note}
  <p style="margin:10px 0 0;font-size:13px;color:#5b667a">
    {html.escape(item.source.title)} · <a href="{html.escape(item.url)}"
    style="color:#1b2a5b">открыть оригинал</a></p>
</article>"""
        )

    document = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{html.escape(digest.title)}</title></head>
<body style="margin:0;padding:32px;background:#ffffff;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0e1428">
<div style="max-width:680px;margin:0 auto">
  <h1 style="margin:0 0 4px;font-size:24px">{html.escape(digest.title)}</h1>
  <p style="margin:0 0 28px;font-size:13px;color:#5b667a">
    Получатель: {html.escape(digest.recipient)} · {generated} · материалов: {len(included)}</p>
  {"".join(blocks)}
</div></body></html>"""
    return PlainTextResponse(document, media_type="text/html; charset=utf-8")
