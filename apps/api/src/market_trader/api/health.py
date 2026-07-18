from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from market_trader.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    trading_mode: Literal["paper"]
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        trading_mode="paper",
        version=settings.app_version,
    )
