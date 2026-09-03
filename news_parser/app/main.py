import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import get_settings
from app.database import get_session_factory, init_db
from app.llm_topics import refresh_all_periods
from app.parser_service import parse_all_channels
from app.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def _initial_warmup() -> None:
    """Первичный парс/обновление топиков. Гоняется в фоне, чтобы НЕ блокировать
    старт uvicorn (иначе сервер не биндит :8000, пока висит коннект к Telegram,
    и k8s-проба валит под). Периодический парс всё равно делает scheduler."""
    session = get_session_factory()()
    try:
        await parse_all_channels(session)
        await refresh_all_periods(session)
    except Exception:
        logger.warning("Initial parse/topics refresh failed", exc_info=True)
        await session.rollback()
    finally:
        await session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialized")

    settings = get_settings()
    if settings.telegram_proxy.strip():
        logger.info("TELEGRAM_PROXY is set: %s", settings.telegram_proxy.split("@")[-1])
    else:
        logger.info("TELEGRAM_PROXY is not set (direct connection)")

    # В фоне — не блокируем готовность сервера на Telegram.
    asyncio.create_task(_initial_warmup())

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("Background scheduler started")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Telegram News Topics API",
    description="Парсер Telegram-каналов и выделение топиков через LLM",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
