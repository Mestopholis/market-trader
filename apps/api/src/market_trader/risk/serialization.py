from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from market_trader.domain.time import ensure_utc

_DISPLAY_ONLY_FIELDS = frozenset({"display_note", "explanation"})


def canonical_record(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical decimal must be finite")
        return str(value)
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: canonical_record(getattr(value, item.name))
            for item in fields(value)
            if item.name not in _DISPLAY_ONLY_FIELDS
        }
    if isinstance(value, Mapping):
        return {
            str(key): canonical_record(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _DISPLAY_ONLY_FIELDS
        }
    if isinstance(value, tuple | list):
        return [canonical_record(item) for item in value]
    raise TypeError(f"unsupported canonical value: {type(value)!r}")


def stable_digest(value: object) -> str:
    encoded = json.dumps(
        canonical_record(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_key(*parts: object) -> str:
    return stable_digest(parts)
