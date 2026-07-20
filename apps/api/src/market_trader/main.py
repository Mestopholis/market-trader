from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from market_trader.api.dashboard import router as dashboard_router
from market_trader.api.health import router as health_router
from market_trader.api.market_state import MarketStateUnavailableResponse
from market_trader.api.market_state import router as market_state_router
from market_trader.api.paper import router as paper_router
from market_trader.config import get_settings
from market_trader.market_calendar.models import CalendarUnavailableError


async def calendar_unavailable_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    unavailable = MarketStateUnavailableResponse()
    return JSONResponse(
        status_code=503,
        content=unavailable.model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Market Trader API",
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    application.add_exception_handler(
        CalendarUnavailableError,
        calendar_unavailable_handler,
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(market_state_router, prefix="/api")
    application.include_router(dashboard_router, prefix="/api/dashboard")
    application.include_router(paper_router, prefix="/api/paper")
    return application


app = create_app()
