import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.database import get_session_factory
from app.llm_topics import refresh_all_periods
from app.parser_service import parse_all_channels

logger = logging.getLogger(__name__)


async def _run_parse_job() -> None:
    session = get_session_factory()()
    try:
        await parse_all_channels(session)
    except Exception:
        logger.exception("Parse job failed")
        await session.rollback()
    finally:
        await session.close()


async def _run_topics_job() -> None:
    session = get_session_factory()()
    try:
        await refresh_all_periods(session)
    except Exception:
        logger.exception("Topics refresh job failed")
        await session.rollback()
    finally:
        await session.close()


def setup_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _run_parse_job,
        "interval",
        minutes=settings.parse_interval_minutes,
        id="parse_channels",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_topics_job,
        "interval",
        minutes=settings.topics_refresh_interval_minutes,
        id="refresh_topics",
        replace_existing=True,
    )
    return scheduler
