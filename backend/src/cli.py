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
    ("sozd", "regulator", "https://sozd.duma.gov.ru/oz", "СОЗД — законопроекты Госдумы"),
    ("web", "regulator", "https://regulation.gov.ru/projects", "regulation.gov.ru — проекты НПА"),
    ("telegram", "telegram", "https://t.me/government_rus", "Правительство РФ — сводки"),
    ("rss", "media", "https://telesputnik.ru/rss", "Телеспутник"),
    ("rss", "media", "https://www.vedomosti.ru/rss/news", "Ведомости"),
]


@app.command("init-db")
def cmd_init_db() -> None:
    """Создать схему и загрузить стартовые данные."""
    asyncio.run(_initialize_database())


async def _initialize_database() -> None:
    from src.scoring.config import load_scoring_config

    await init_db()
    # Конфиг оценки не хранится в БД: валидируем его при инициализации, чтобы
    # ошибка в весах или шкалах обнаруживалась до первого запуска пайплайна.
    load_scoring_config()
    await _seed_profiles(initialize_schema=False)
    await _seed_sources(initialize_schema=False)
    typer.echo("Схема, профиль компании, источники и конфиг оценки инициализированы")


@app.command("seed-profiles")
def cmd_seed_profiles() -> None:
    """Загрузить профили компании из config/company_profile.yaml (FR-050)."""
    asyncio.run(_seed_profiles())


async def _seed_profiles(*, initialize_schema: bool = True) -> None:
    from sqlalchemy import select

    from src.models import CompanyProfile

    if initialize_schema:
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


async def _seed_sources(*, initialize_schema: bool = True) -> None:
    from sqlalchemy import select

    from src.models import ItemType, Source, SourceCategory, SourceType

    if initialize_schema:
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
                    item_type=(
                        ItemType.ACT if cat is SourceCategory.REGULATOR else ItemType.NEWS
                    ),
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

    # Догоняющая кластеризация считается отдельно: это не обработка материала,
    # и её нулевая длительность занижала бы среднее время в отчёте по SC-003.
    processed = [r for r in results if not r.is_clustering_only]
    catching_up = [r for r in results if r.is_clustering_only]
    scored = sum(1 for r in processed if r.scored)
    typer.echo(f"Обработано {len(processed)}, оценено {scored}")
    if catching_up:
        typer.echo(f"Догоняющая кластеризация ранее обработанных: {len(catching_up)}")
    if processed:
        total_time = sum(r.duration_seconds for r in processed)
        typer.echo(
            f"Среднее время на материал: {total_time / len(processed):.1f} с "
            f"(цель SC-003 — 10-15 с)"
        )
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


@app.command("export-revisions")
def cmd_export_revisions(
    out: Path = typer.Option(
        EVALS_DIR / "revisions.jsonl",
        help="куда записать эталонные метки из журнала правок",
    ),
) -> None:
    """Выгрузить расхождения машина/человек для последующих eval-прогонов — FR-081."""
    asyncio.run(_export_revisions(out))


async def _export_revisions(out: Path) -> None:
    from src.evals.revisions import export_revisions

    await init_db()
    async with get_session_factory()() as session:
        count = await export_revisions(session, out)
    typer.echo(f"Выгружено правок: {count} → {out}")


@app.command("verify-formula")
def cmd_verify_formula(
    dataset: Path = typer.Option(EVALS_DIR / "registry_46.jsonl", help="эталонный датасет"),
) -> None:
    """Сверить формулу индекса с числами из Excel заказчика — задача T014.

    Если наша формула расходится с реестром, вся оценка бессмысленна: методика
    принадлежит заказчику, а не нам.
    """
    from src.evals.formula_check import verify_against_registry

    try:
        report = verify_against_registry(dataset)
    except Exception as exc:
        typer.echo(f"Не удалось прочитать эталон {dataset}: {exc}", err=True)
        raise typer.Exit(1) from exc

    index_mismatches = report["index_mismatches"]
    category_mismatches = report["category_mismatches"]
    final_category_mismatches = report["final_category_mismatches"]

    typer.echo(f"Проверено фактических карточек: {report['checked']}")
    typer.echo(f"Совпало по индексу: {report['matched']}")
    typer.echo(f"Index mismatches: {len(index_mismatches)}")
    typer.echo(f"Category mismatches: {len(category_mismatches)}")
    typer.echo(f"Final category mismatches: {len(final_category_mismatches)}")

    if index_mismatches:
        typer.echo("\nРасхождения индекса:")
        for m in index_mismatches:
            typer.echo(
                f"  #{m['id']}: наш {m['computed']} против {m['expected']} в реестре "
                f"(баллы {m['scores']})"
            )

    if category_mismatches:
        typer.echo("\nРасхождения базовой категории:")
        for m in category_mismatches:
            typer.echo(f"  #{m['id']}: наша {m['computed']} против {m['expected']} в реестре")

    if final_category_mismatches:
        typer.echo("\nРасхождения итоговой категории:")
        for m in final_category_mismatches:
            typer.echo(
                f"  #{m['id']}: наша {m['computed']} против {m['expected']} в реестре "
                f"(индекс {m['index']})"
            )

    if index_mismatches or category_mismatches or final_category_mismatches:
        raise typer.Exit(1)

    typer.echo("Формула воспроизводит 42 фактические карточки реестра точно")


@app.command("seed-demo")
def cmd_seed_demo(
    limit: int = typer.Option(24, help="сколько карточек реестра загрузить"),
) -> None:
    """Наполнить базу карточками из реестра заказчика — для проверки интерфейса.

    Берутся реальные карточки с проставленными человеком баллами, индекс
    пересчитывается нашей формулой. Модель не вызывается: это фикстура для
    отладки интерфейса и демонстрации, а не имитация работы конвейера.
    """
    asyncio.run(_seed_demo(limit))


async def _seed_demo(limit: int) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from src.evals.registry import load_dataset
    from src.models import (
        Assessment,
        AssessmentScheme,
        Author,
        CompanyProfile,
        Item,
        ItemType,
        Source,
        SourceCategory,
        SourceType,
        Summary,
    )
    from src.pipeline.normalize import content_hash
    from src.scoring import get_scoring_config
    from src.scoring import score as compute_score

    dataset = EVALS_DIR / "registry_46.jsonl"
    if not dataset.exists():
        typer.echo("Сначала соберите эталон: python -m src.cli parse-registry", err=True)
        raise typer.Exit(1)

    await init_db()
    rows = load_dataset(dataset)[:limit]
    config = get_scoring_config()

    async with get_session_factory()() as session:
        # Реестр — материалы GS Labs, поэтому профиль берётся по slug, а не
        # «какой сейчас активен»: активный меняется переключателем в интерфейсе.
        profile = (
            await session.execute(select(CompanyProfile).where(CompanyProfile.slug == "gs-labs"))
        ).scalar_one_or_none()
        if profile is None:
            typer.echo("Нет профиля gs-labs: python -m src.cli seed-profiles", err=True)
            raise typer.Exit(1)

        source = (
            await session.execute(select(Source).where(Source.url == "internal://registry"))
        ).scalar_one_or_none()
        if source is None:
            source = Source(
                type=SourceType.MANUAL,
                category=SourceCategory.REGULATOR,
                item_type=ItemType.ACT,
                url="internal://registry",
                title="Реестр заказчика",
                is_active=False,
            )
            session.add(source)
            await session.flush()

        created = 0
        for offset, row in enumerate(rows):
            url = f"internal://registry/{row['id']}"
            if (await session.execute(select(Item).where(Item.url == url))).scalar_one_or_none():
                continue

            text = row.get("text") or row["identifier"]
            is_act = row["kind"] == "act"
            item = Item(
                source_id=source.id,
                url=url,
                title=row["identifier"][:900],
                raw_text=text,
                content_hash=content_hash(text),
                published_at=datetime.now(UTC) - timedelta(hours=offset * 3 + 1),
                item_type=ItemType.ACT if is_act else ItemType.NEWS,
                topic="regulatory" if is_act else "trends",
                act_identifier=row["identifier"][:512] if is_act else None,
                tags=["реестр"],
                processed_at=datetime.now(UTC),
            )
            session.add(item)
            await session.flush()

            scheme = AssessmentScheme.NPA_K1_K6 if is_act else AssessmentScheme.NEWS_H1_H4
            flags = (
                [config.escalation_flags[0].text]
                if row.get("gold_escalation") and config.escalation_flags
                else []
            )
            computed = compute_score(row["gold_scores"], scheme, flags, config=config)

            sentences = [s.strip() for s in text.split(". ") if len(s.strip()) > 25][:3]
            claims = [
                {
                    "statement": s if s.endswith(".") else f"{s}.",
                    "quote": s,
                    "quote_found": True,
                    "entailed": True,
                    "char_start": text.find(s),
                    "char_end": text.find(s) + len(s),
                    "reject_reason": None,
                }
                for s in sentences
            ]
            session.add(
                Summary(
                    item_id=item.id,
                    text=" ".join(c["statement"] for c in claims),
                    claims=claims,
                    entities={
                        "who": [row.get("doc_type", "")] if row.get("doc_type") else [],
                        "what": row["identifier"][:200],
                        "when": row.get("stage", ""),
                        "consequences": "",
                    },
                    author=Author.AI,
                    model="registry-fixture",
                    prompt_version="summarize/v1",
                    is_current=True,
                )
            )
            session.add(
                Assessment(
                    item_id=item.id,
                    profile_id=profile.id,
                    scheme=computed.scheme,
                    scores=computed.scores,
                    rationales={
                        code: f"Балл {score} по шкале критерия {code} — из реестра заказчика."
                        for code, score in computed.scores.items()
                    },
                    index_value=computed.index_value,
                    category=computed.category,
                    escalation_flags=computed.escalation_flags,
                    final_category=computed.final_category,
                    author=Author.AI,
                    model="registry-fixture",
                    prompt_version="score/v1",
                    is_current=True,
                )
            )
            item.is_relevant = computed.is_relevant
            created += 1

        await session.commit()

    typer.echo(f"Загружено карточек: {created}")


@app.command("evaluate")
def cmd_evaluate(
    dataset: Path = typer.Option(EVALS_DIR / "registry_46.jsonl", help="эталонный датасет"),
    limit: int = typer.Option(0, help="ограничить число карточек (0 — все)"),
    out: Path = typer.Option(EVALS_DIR / "last-report.txt", help="куда сохранить отчёт"),
    profile: str = typer.Option("gs-labs", help="slug профиля компании, от лица которой оцениваем"),
) -> None:
    """Измерить качество оценки на эталоне заказчика — задача T083.

    Печатает базовую ставку и baseline большинства рядом с любой долей:
    accuracy без них ничего не значит, потому что большинство материалов
    нерелевантны и тривиальный классификатор набирает высокий процент.
    """
    asyncio.run(_evaluate(dataset, limit or None, out, profile))


async def _evaluate(dataset: Path, limit: int | None, out: Path, profile_slug: str) -> None:
    from sqlalchemy import select

    from src.evals.quality import dump_cards, evaluate, format_report
    from src.llm import build_provider
    from src.models import CompanyProfile

    if not dataset.exists():
        typer.echo(f"Нет эталона: {dataset}. Сначала: python -m src.cli parse-registry", err=True)
        raise typer.Exit(1)
    if not get_settings().llm_configured:
        typer.echo("LLM не настроен: задайте LLM_API_KEY в backend/.env", err=True)
        raise typer.Exit(1)

    await init_db()
    async with get_session_factory()() as session:
        # Профиль задаётся явно, а не берётся «какой сейчас активен». Активный
        # профиль меняется переключателем в интерфейсе, и замер, зависящий от
        # состояния UI, невоспроизводим: первый прогон эталона GS Labs ушёл
        # с профилем «Триколор», потому что его переключили при проверке экранов.
        profile = (
            await session.execute(select(CompanyProfile).where(CompanyProfile.slug == profile_slug))
        ).scalar_one_or_none()
        if profile is None:
            typer.echo(
                f"Нет профиля «{profile_slug}». Доступные: python -m src.cli seed-profiles",
                err=True,
            )
            raise typer.Exit(1)
        context = profile.as_prompt_context()
        profile_name = profile.name

    report = await evaluate(dataset, build_provider(), context, limit)
    text = format_report(report)
    typer.echo(text)

    header = (
        f"Отчёт о качестве оценки\n"
        f"Профиль: {profile_name}\nМодель: {get_settings().llm_model}\n"
        f"Дата: {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"{'=' * 70}\n\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + text + "\n", encoding="utf-8")
    # Имя разбора выводится из имени отчёта: при сравнении моделей прогоны
    # идут параллельно, и общий файл они бы затирали друг у друга.
    cards_path = out.with_name(f"{out.stem}-cards.jsonl")
    cards_path.write_text(dump_cards(report) + "\n", encoding="utf-8")
    typer.echo(f"\nОтчёт сохранён: {out}\nРазбор по карточкам: {cards_path}")


@app.command("export-openapi")
def cmd_export_openapi(
    out: Path = typer.Option(
        REPO_ROOT / "specs" / "001-ai-monitoring-center" / "contracts" / "openapi.generated.json",
        help="куда писать спецификацию",
    ),
) -> None:
    """Выгрузить фактическую спецификацию API.

    Из неё генерируются типы фронтенда. Пока типы писались руками, они молча
    разошлись с контрактом: список досье объявлялся как ActDetail, хотя backend
    отдаёт ActCard без поля essence — компилятор промолчал, а браузер упал.
    """
    from src.api.main import app as fastapi_app

    spec = fastapi_app.openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Записано: {out} ({len(spec['paths'])} путей)")


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
