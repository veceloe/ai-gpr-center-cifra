"""Периодический сбор и обработка — FR-005, research R-07.

APScheduler внутри процесса приложения. Брокер, очередь и воркеры не вводятся:
на объёмах прототипа это сложность, которую нечем оправдать, и ещё один способ
сорвать демонстрацию.

Два интервала вместо индивидуальной частоты на источник: 15 минут для СМИ
и Telegram, 60 для регуляторов — заказчик признал сверхгибкую настройку
избыточной для прототипа.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings
from src.db import get_session_factory

logger = logging.getLogger(__name__)

PROCESS_BATCH_LIMIT = 20


async def collect_job() -> None:
    from src.collectors import collect_active_sources

    settings = get_settings()
    async with get_session_factory()() as session:
        try:
            results = await collect_active_sources(session, settings.fetch_limit_per_source)
            created = sum(r.created for r in results)
            failed = [r for r in results if r.error]
            logger.info("Сбор завершён: новых материалов %s, источников с ошибкой %s", created, len(failed))
        except Exception:
            logger.exception("Задача сбора провалилась")
            await session.rollback()


async def process_job() -> None:
    from src.llm import build_provider
    from src.pipeline.runner import process_unprocessed

    settings = get_settings()
    if not settings.llm_configured:
        logger.debug("Обработка пропущена: LLM не настроен")
        return

    async with get_session_factory()() as session:
        try:
            results = await process_unprocessed(session, build_provider(), PROCESS_BATCH_LIMIT)
            scored = sum(1 for r in results if r.scored)
            logger.info("Обработка: %s материалов, оценено %s", len(results), scored)
        except Exception:
            logger.exception("Задача обработки провалилась")
            await session.rollback()


def setup_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        collect_job,
        "interval",
        minutes=settings.poll_interval_media_min,
        id="collect_sources",
        replace_existing=True,
        max_instances=1,
    )
    # Обработка чаще сбора: материалы должны доезжать до ленты за 15 минут (SC-002),
    # а не ждать следующего цикла сбора.
    scheduler.add_job(
        process_job,
        "interval",
        minutes=max(settings.poll_interval_media_min // 3, 2),
        id="process_items",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler
