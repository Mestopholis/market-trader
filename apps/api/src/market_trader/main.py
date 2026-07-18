from fastapi import FastAPI

from market_trader.api.health import router as health_router
from market_trader.api.market_state import router as market_state_router
from market_trader.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Market Trader API",
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(market_state_router, prefix="/api")
    return application


app = create_app()
