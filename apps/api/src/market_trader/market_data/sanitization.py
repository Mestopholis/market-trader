import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal

MAX_STRING_LENGTH = 2_048
MAX_COLLECTION_ITEMS = 1_000
_SECRET_FRAGMENTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "api_key",
    "account",
)

type SanitizedValue = (
    None | bool | int | float | str | list[SanitizedValue] | dict[str, SanitizedValue]
)


def sanitize_payload(value: object) -> SanitizedValue:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"type": "float", "value": "non-finite"}
    if isinstance(value, str):
        return value[:MAX_STRING_LENGTH]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "length": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value[:MAX_COLLECTION_ITEMS]]
    type_name = type(value).__name__[:MAX_STRING_LENGTH]
    return {
        "type": type_name,
        "sha256": hashlib.sha256(type_name.encode("utf-8")).hexdigest(),
    }


def canonical_json(value: SanitizedValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_digest(value: SanitizedValue) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def ingestion_key(source: str, event_id: str, fixture_schema_version: int) -> str:
    identity: SanitizedValue = {
        "source": source,
        "event_id": event_id,
        "fixture_schema_version": fixture_schema_version,
    }
    return f"ing_{canonical_digest(identity)}"


def _sanitize_mapping(value: Mapping[object, object]) -> dict[str, SanitizedValue]:
    keyed = sorted((str(key)[:MAX_STRING_LENGTH], item) for key, item in value.items())
    sanitized: dict[str, SanitizedValue] = {}
    for key, item in keyed[:MAX_COLLECTION_ITEMS]:
        sanitized[key] = "[REDACTED]" if _is_secret_key(key) else sanitize_payload(item)
    return sanitized


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(" ", "_")
    return any(fragment in normalized for fragment in _SECRET_FRAGMENTS)
