import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"
_MAX_IDENTIFIER_LENGTH = 64
_VALID_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


@dataclass(frozen=True)
class CorrelationContext:
    request_id: str
    correlation_id: str


def new_request_id() -> str:
    return _new_prefixed_id("req")


def new_correlation_id() -> str:
    return _new_prefixed_id("corr")


def resolve_correlation_context(headers: Mapping[str, str]) -> CorrelationContext:
    inbound = _get_header(headers, CORRELATION_ID_HEADER)
    correlation_id = (
        inbound if inbound is not None and is_valid_identifier(inbound) else new_correlation_id()
    )
    return CorrelationContext(request_id=new_request_id(), correlation_id=correlation_id)


def correlation_response_headers(context: CorrelationContext) -> dict[str, str]:
    return {
        REQUEST_ID_HEADER: context.request_id,
        CORRELATION_ID_HEADER: context.correlation_id,
    }


def is_valid_identifier(value: str) -> bool:
    return len(value) <= _MAX_IDENTIFIER_LENGTH and _VALID_IDENTIFIER.fullmatch(value) is not None


def _new_prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    if name in headers:
        return headers[name]
    lowered = name.casefold()
    for key, value in headers.items():
        if key.casefold() == lowered:
            return value
    return None
