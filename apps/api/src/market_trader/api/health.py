from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from market_trader.config import get_settings
from market_trader.db.engine import create_engine_from_url
from market_trader.system_state.models import SystemReadiness
from market_trader.system_state.service import collect_system_state

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    trading_mode: Literal["paper"]
    version: str
    database: Literal["ok", "unavailable"]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        trading_mode="paper",
        version=settings.app_version,
        database=database_state(settings.database_url),
    )


@router.get("/readiness", response_model=SystemReadiness)
def readiness() -> SystemReadiness:
    settings = get_settings()
    return collect_system_state(settings.database_url)


def database_state(database_url: str) -> Literal["ok", "unavailable"]:
    engine: Engine | None = None
    try:
        engine = create_engine_from_url(database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        return "unavailable"
    finally:
        if engine is not None:
            engine.dispose()
    return "ok"
