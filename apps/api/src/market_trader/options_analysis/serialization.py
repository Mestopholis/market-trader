import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


def canonical_record(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return canonical_record(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): canonical_record(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, tuple | list):
        return [canonical_record(item) for item in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical decimal must be finite")
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return canonical_record(value.value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"unsupported canonical value: {type(value)!r}")


def stable_digest(value: object) -> str:
    encoded = json.dumps(
        canonical_record(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
