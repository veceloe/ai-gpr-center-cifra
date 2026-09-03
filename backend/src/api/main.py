"""Точка входа приложения.

Прогрев вынесен в фон намеренно: если стартовать сервер только после первого сбора,
порт не биндится, пока висит коннект к источнику, и health-проба деплоя валит
контейнер. Приём, унаследованный из драфта news_parser, — он там был решён верно.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import api_router
from src.config import get_settings
from src.db import init_db
from src.scheduler import setup_scheduler, warmup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("База инициализирована")

    settings = get_settings()
    if not settings.llm_configured:
        logger.warning(
            "LLM_API_KEY не задан: сбор и лента работают, обработка материалов — нет"
        )
    if not settings.telegram_configured:
        logger.warning("Telegram не настроен: источники этого типа будут отдавать ошибку")

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("Планировщик запущен")
    # Не await: иначе healthcheck деплоя не дождётся открытия порта.
    asyncio.create_task(warmup(), name="startup-warmup")

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Интеллектуальный центр PR/GR-мониторинга",
    description=(
        "Сбор отраслевых новостей и НПА, заземлённая саммаризация и оценка влияния "
        "на конкретную компанию по методике заказчика."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Авторизация вне скоупа MVP по решению заказчика, поэтому CORS открыт:
# прототип запускается локально и на демо-сервере без домена.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


def run() -> None:
    settings = get_settings()
    import uvicorn

    uvicorn.run("src.api.main:app", host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    run()
