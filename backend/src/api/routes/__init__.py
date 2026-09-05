"""Маршруты API. Префикс /api задаётся в main.py по контракту."""

from fastapi import APIRouter

from src.api.routes import feed, health, items, profiles, sources, stories

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(feed.router)
api_router.include_router(items.router)
api_router.include_router(sources.router)
api_router.include_router(profiles.router)
api_router.include_router(stories.router)

__all__ = ["api_router"]
