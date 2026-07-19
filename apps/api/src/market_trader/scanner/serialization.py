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

_SCORE_FIELDS = {"cap", "final", "pre_cap", "score", "signed_score"}
_SCORE_QUANTUM = Decimal("0.000001")


def canonical_record(value: object) -> SanitizedValue:
    """Convert a scanner value to its stable, sanitized JSON representation."""
    return sanitize_payload(_canonical_value(value))


def stable_digest(value: object) -> str:
    return canonical_digest(canonical_record(value))


def _canonical_value(value: object, *, field_name: str | None = None) -> object:
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        if field_name in _SCORE_FIELDS:
            return format(value.quantize(_SCORE_QUANTUM), "f")
        return str(value)
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name), field_name=item.name)
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item, field_name=str(key))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value
