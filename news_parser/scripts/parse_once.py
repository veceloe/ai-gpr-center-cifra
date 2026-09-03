"""Разовый запуск парсинга и пересчёта топиков."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import get_session_factory, init_db
from app.llm_topics import refresh_all_periods
from app.parser_service import parse_all_channels


async def main() -> None:
    await init_db()
    session = get_session_factory()()
    try:
        count = await parse_all_channels(session)
        print(f"Parsed new posts: {count}")
        stats = await refresh_all_periods(session)
        print(f"Topics refreshed: {stats}")
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
