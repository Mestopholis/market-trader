import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from market_trader.api.auth import (
    AuthRequiredError,
    CsrfFailedError,
    auth_required_exception_handler,
    csrf_failed_exception_handler,
)
from market_trader.api.auth import (
    router as auth_router,
)
from market_trader.api.dashboard import router as dashboard_router
from market_trader.api.health import router as health_router
from market_trader.api.market_state import MarketStateUnavailableResponse
from market_trader.api.market_state import router as market_state_router
from market_trader.api.paper import router as paper_router
from market_trader.config import get_settings
from market_trader.market_calendar.models import CalendarUnavailableError
from market_trader.observability.correlation import (
    CorrelationContext,
    correlation_response_headers,
    resolve_correlation_context,
)
from market_trader.observability.errors import (
    request_correlation_context,
    safe_exception_summary,
    safe_internal_error_response,
)
from market_trader.observability.logging import log_structured_event


def _path_template(request: Request) -> str:
    return request.url.path


def _log_completed_request(
    request: Request,
    *,
    context: CorrelationContext,
    status_code: int,
    latency_ms: float,
) -> None:
    log_structured_event(
        {
            "event": "api.request.completed",
            "component": "api",
            "method": request.method,
            "path_template": _path_template(request),
            "status_code": status_code,
            "latency_ms": round(latency_ms, 3),
            "request_id": context.request_id,
            "correlation_id": context.correlation_id,
        }
    )


def _log_failed_request(
    request: Request,
    *,
    context: CorrelationContext,
    error: Exception,
    latency_ms: float,
) -> None:
    log_structured_event(
        {
            "event": "api.request.failed",
            "component": "api",
            "method": request.method,
            "path_template": _path_template(request),
            "status_code": 500,
            "latency_ms": round(latency_ms, 3),
            "request_id": context.request_id,
            "correlation_id": context.correlation_id,
            "error_code": "internal_error",
            "error": safe_exception_summary(error),
        }
    )


async def calendar_unavailable_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    unavailable = MarketStateUnavailableResponse()
    headers = {"Cache-Control": "no-store"}
    context = request_correlation_context(_request)
    if context is not None:
        headers.update(correlation_response_headers(context))
    return JSONResponse(
        status_code=503,
        content=unavailable.model_dump(mode="json"),
        headers=headers,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Market Trader API",
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    @application.middleware("http")
    async def structured_diagnostics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        context = resolve_correlation_context(dict(request.headers))
        request.state.correlation_context = context
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as error:
            latency_ms = (time.perf_counter() - started) * 1000
            _log_failed_request(
                request,
                context=context,
                error=error,
                latency_ms=latency_ms,
            )
            return safe_internal_error_response(context)
        latency_ms = (time.perf_counter() - started) * 1000
        for name, value in correlation_response_headers(context).items():
            response.headers[name] = value
        _log_completed_request(
            request,
            context=context,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        return response

    application.add_exception_handler(
        CalendarUnavailableError,
        calendar_unavailable_handler,
    )
    application.add_exception_handler(AuthRequiredError, auth_required_exception_handler)
    application.add_exception_handler(CsrfFailedError, csrf_failed_exception_handler)
    application.include_router(health_router, prefix="/api")
    application.include_router(auth_router, prefix="/api")
    application.include_router(market_state_router, prefix="/api")
    application.include_router(dashboard_router, prefix="/api/dashboard")
    application.include_router(paper_router, prefix="/api/paper")
    return application


app = create_app()
