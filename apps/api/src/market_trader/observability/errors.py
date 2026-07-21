from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from market_trader.observability.correlation import (
    CorrelationContext,
    correlation_response_headers,
)
from market_trader.observability.redaction import redact_value


class SafeErrorResponse(BaseModel):
    code: str
    summary: str
    correlation_id: str
    remediation: str


def safe_internal_error_response(context: CorrelationContext) -> JSONResponse:
    body = SafeErrorResponse(
        code="internal_error",
        summary="An internal error occurred.",
        correlation_id=context.correlation_id,
        remediation="Use the correlation id to inspect local structured logs.",
    )
    return JSONResponse(
        status_code=500,
        content=body.model_dump(mode="json"),
        headers={
            **correlation_response_headers(context),
            "Cache-Control": "no-store",
        },
    )


def safe_exception_summary(error: Exception) -> dict[str, object]:
    return {
        "exception_type": type(error).__name__,
        "message": redact_value(str(error)),
    }


def request_correlation_context(request: Request) -> CorrelationContext | None:
    value = getattr(request.state, "correlation_context", None)
    return value if isinstance(value, CorrelationContext) else None
