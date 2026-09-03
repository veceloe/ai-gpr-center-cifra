"""Живость сервиса — используется health gate деплоя (specs/002-deploy)."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
