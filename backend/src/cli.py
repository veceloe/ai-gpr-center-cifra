"""Командная строка: инициализация, сиды, разовый сбор, измерение качества."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import typer
import yaml

from src.config import BACKEND_DIR, get_settings
from src.db import get_session_factory, init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
app = typer.Typer(add_completion=False, help="Интеллектуальный центр PR/GR-мониторинга")

REPO_ROOT = BACKEND_DIR.parent
EVALS_DIR = REPO_ROOT / "evals"

# Источники для MVP — docs/sources.md, отбор «5 источников трёх типов» (FR-001, SC-009).
SEED_SOURCES = [
    ("web", "regulator", "https://sozd.duma.gov.ru/oz", "СОЗД — законопроекты Госдумы"),
    ("web", "regulator", "https://regulation.gov.ru/projects", "regulation.gov.ru — проекты НПА"),
    ("telegram", "telegram", "https://t.me/government_rus", "Правительство РФ — сводки"),
    ("telegram", "telegram", "https://t.me/arppsoft", "АРПП — новости"),
    ("rss", "media", "https://telesputnik.ru/rss", "Телеспутник"),
    ("rss", "media", "https://www.vedomosti.ru/rss/news", "Ведомости"),
]


@app.command("init-db")
def cmd_init_db() -> None:
    """Создать схему базы данных."""
    asyncio.run(init_db())
    typer.echo("Схема создана")


@app.command("seed-profiles")
def cmd_seed_profiles() -> None:
    """Загрузить профили компании из config/company_profile.yaml (FR-050)."""
    asyncio.run(_seed_profiles())


async def _seed_profiles() -> None:
    from sqlalchemy import select

    from src.models import CompanyProfile

    await init_db()
    settings = get_settings()
    with Path(settings.company_profile_path).open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)

    async with get_session_factory()() as session:
        for entry in payload["profiles"]:
            existing = (
                await session.execute(
                    select(CompanyProfile).where(CompanyProfile.slug == entry["slug"])
                )
            ).scalar_one_or_none()
            target = existing or CompanyProfile(slug=entry["slug"])
            target.name = entry["name"]
            target.industry = entry["industry"].strip()
            target.products = entry.get("products", [])
            target.regimes = entry.get("regimes", [])
            target.risk_areas = entry.get("risk_areas", [])
            target.growth_areas = entry.get("growth_areas", [])
            target.competitors = entry.get("competitors", [])
            target.noise_markers = entry.get("noise_markers", [])
            target.is_active = bool(entry.get("is_active", False))
            if existing is None:
                session.add(target)
            typer.echo(f"{'обновлён' if existing else 'создан'}: {entry['slug']}")
        await session.commit()


@app.command("seed-sources")
def cmd_seed_sources() -> None:
    """Загрузить базовый набор источников из docs/sources.md (FR-001)."""
    asyncio.run(_seed_sources())


async def _seed_sources() -> None:
    from sqlalchemy import select

    from src.models import Source, SourceCategory, SourceType

    await init_db()
    settings = get_settings()
    async with get_session_factory()() as session:
        for type_, category, url, title in SEED_SOURCES:
            if (await session.execute(select(Source).where(Source.url == url))).scalar_one_or_none():
                typer.echo(f"уже есть: {title}")
                continue
            cat = SourceCategory(category)
            session.add(
                Source(
                    type=SourceType(type_),
                    category=cat,
                    url=url,
                    title=title,
                    poll_interval_min=(
                        settings.poll_interval_regulator_min
                        if cat is SourceCategory.REGULATOR
                        else settings.poll_interval_media_min
                    ),
                )
            )
            typer.echo(f"добавлен: {title}")
        await session.commit()


@app.command("collect")
def cmd_collect(source_id: int | None = typer.Option(None, help="только этот источник")) -> None:
    """Разовый сбор из активных источников."""
    asyncio.run(_collect(source_id))


async def _collect(source_id: int | None) -> None:
    from sqlalchemy import select

    from src.collectors import collect_active_sources, collect_source
    from src.models import Source

    await init_db()
    settings = get_settings()
    async with get_session_factory()() as session:
        if source_id is not None:
            source = await session.get(Source, source_id)
            if source is None:
                typer.echo(f"Источник {source_id} не найден", err=True)
                raise typer.Exit(1)
            results = [await collect_source(session, source, settings.fetch_limit_per_source)]
            await session.commit()
        else:
            results = await collect_active_sources(session, settings.fetch_limit_per_source)

        titles = {
            s.id: s.title
            for s in (await session.execute(select(Source))).scalars().all()
        }

    for r in results:
        status = f"ошибка: {r.error}" if r.error else f"новых {r.created}, обновлено {r.updated}"
        typer.echo(f"{titles.get(r.source_id, r.source_id)}: получено {r.fetched}, {status}")


@app.command("process")
def cmd_process(limit: int = typer.Option(20, help="сколько материалов обработать")) -> None:
    """Обработать необработанные материалы: саммари, заземление, классификация, оценка."""
    asyncio.run(_process(limit))


async def _process(limit: int) -> None:
    from src.llm import build_provider
    from src.pipeline.runner import process_unprocessed

    await init_db()
    if not get_settings().llm_configured:
        typer.echo("LLM не настроен: задайте LLM_API_KEY и LLM_BASE_URL в backend/.env", err=True)
        raise typer.Exit(1)

    async with get_session_factory()() as session:
        results = await process_unprocessed(session, build_provider(), limit)

    if not results:
        typer.echo("Нет материалов для обработки")
        return

    scored = sum(1 for r in results if r.scored)
    total_time = sum(r.duration_seconds for r in results)
    typer.echo(f"Обработано {len(results)}, оценено {scored}")
    typer.echo(f"Среднее время на материал: {total_time / len(results):.1f} с (цель SC-003 — 10-15 с)")
    for r in results:
        if r.grounding:
            g = r.grounding
            typer.echo(
                f"  #{r.item_id}: утверждений {g.get('total', 0)}, принято {g.get('accepted', 0)}, "
                f"нет цитаты {g.get('quote_not_found', 0)}, не подтверждено {g.get('not_entailed', 0)}"
            )
        if r.error:
            typer.echo(f"  #{r.item_id}: {r.error}")


@app.command("parse-registry")
def cmd_parse_registry(
    xlsx: Path = typer.Option(
        REPO_ROOT / "context" / "Для_ИТМО_мониторинг_НПА_и_отрасли.xlsx",
        help="Excel-реестр заказчика",
    ),
    out: Path = typer.Option(EVALS_DIR / "registry_46.jsonl", help="куда писать эталон"),
) -> None:
    """Собрать эталонный датасет из реестра заказчика — задача T017.

    У каждой карточки уже проставлены человеком баллы, индекс и категория. Это готовая
    разметка, которую надо только распарсить: другого эталона у нас нет.
    """
    from src.evals.registry import parse_registry

    rows = parse_registry(xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    npa = sum(1 for r in rows if r["kind"] == "act")
    typer.echo(f"Записано {len(rows)} карточек в {out} (НПА {npa}, новостей {len(rows) - npa})")


@app.command("verify-formula")
def cmd_verify_formula(
    dataset: Path = typer.Option(EVALS_DIR / "registry_46.jsonl", help="эталонный датасет"),
) -> None:
    """Сверить формулу индекса с числами из Excel заказчика — задача T014.

    Если наша формула расходится с реестром, вся оценка бессмысленна: методика
    принадлежит заказчику, а не нам.
    """
    from src.evals.formula_check import verify_against_registry

    report = verify_against_registry(dataset)
    typer.echo(f"Проверено карточек: {report['checked']}")
    typer.echo(f"Совпало с реестром: {report['matched']}")
    if report["mismatches"]:
        typer.echo("\nРасхождения:")
        for m in report["mismatches"]:
            typer.echo(
                f"  #{m['id']}: наш {m['computed']} против {m['expected']} в реестре "
                f"(баллы {m['scores']})"
            )
        raise typer.Exit(1)
    typer.echo("Формула воспроизводит методику заказчика точно")


@app.command("telegram-login")
def cmd_telegram_login() -> None:
    """Однократная авторизация Telegram: печатает TELEGRAM_STRING_SESSION (ADR-0008)."""
    asyncio.run(_telegram_login())


async def _telegram_login() -> None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    from src.collectors.telegram import parse_proxy

    settings = get_settings()
    if not (settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_phone):
        typer.echo(
            "Нужны TELEGRAM_API_ID, TELEGRAM_API_HASH и TELEGRAM_PHONE в backend/.env", err=True
        )
        raise typer.Exit(1)

    proxy = parse_proxy(settings.telegram_proxy)
    client = TelegramClient(
        StringSession(),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        **({"proxy": proxy} if proxy else {}),
    )
    await client.start(phone=settings.telegram_phone)
    me = await client.get_me()
    typer.echo(f"\nАвторизован как {me.first_name} (@{me.username})")
    typer.echo("\nСтрока сессии — положите её в TELEGRAM_STRING_SESSION:\n")
    typer.echo(client.session.save())
    await client.disconnect()


if __name__ == "__main__":
    app()
