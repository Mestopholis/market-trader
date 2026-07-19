from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from market_trader.domain.time import ensure_utc
from market_trader.market_data.sanitization import (
    SanitizedValue,
    canonical_digest,
    sanitize_payload,
)

_SENSITIVE_FRAGMENTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "api_key",
    "account",
    "approval",
    "order",
)


def canonical_record(value: object) -> SanitizedValue:
    return sanitize_payload(_canonical_value(value))


def stable_digest(value: object) -> str:
    return canonical_digest(canonical_record(value))


def _canonical_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _canonical_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(" ", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)
