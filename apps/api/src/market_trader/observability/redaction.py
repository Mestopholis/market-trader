import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

REDACTED = "[REDACTED]"
MAX_STRING_LENGTH = 2_048
MAX_COLLECTION_ITEMS = 100

type RedactedValue = (
    None | bool | int | float | str | list[RedactedValue] | dict[str, RedactedValue]
)

_SECRET_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "csrf",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "credential",
    "database_url",
    "broker_account",
    "account_number",
    "accountnumber",
)

_AUTHORIZATION_VALUE = re.compile(
    r"(?i)(authorization\s*:\s*)(bearer|basic)\s+[^\s,;]+"
)
_DATABASE_URL_WITH_CREDENTIALS = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mssql|oracle)://[^\s/@:]+:[^\s/@]+@[^\s]+"
)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}")
_SCHWAB_TOKEN_HINT = re.compile(r"(?i)\bschwab[-_a-z0-9]*token[-_a-z0-9]*")


def redact_value(value: object) -> RedactedValue:
    return _redact(value, secret_context=False)


def _redact(value: object, *, secret_context: bool) -> RedactedValue:
    if secret_context:
        return REDACTED
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"type": "float", "value": "non-finite"}
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Decimal):
        return _redact_string(str(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "length": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact(item, secret_context=False) for item in value[:MAX_COLLECTION_ITEMS]]
    return {"type": type(value).__name__[:MAX_STRING_LENGTH]}


def _redact_mapping(value: Mapping[object, object]) -> dict[str, RedactedValue]:
    keyed = sorted((str(key)[:MAX_STRING_LENGTH], item) for key, item in value.items())
    redacted: dict[str, RedactedValue] = {}
    for key, item in keyed[:MAX_COLLECTION_ITEMS]:
        redacted[key] = _redact(item, secret_context=_is_secret_key(key))
    return redacted


def _redact_string(value: str) -> str:
    bounded = value[:MAX_STRING_LENGTH]
    if _is_secret_value(bounded):
        return REDACTED
    bounded = _AUTHORIZATION_VALUE.sub(r"\1[REDACTED]", bounded)
    bounded = _DATABASE_URL_WITH_CREDENTIALS.sub(REDACTED, bounded)
    bounded = _BEARER_VALUE.sub(REDACTED, bounded)
    return bounded


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(" ", "_")
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)


def _is_secret_value(value: str) -> bool:
    return bool(
        _DATABASE_URL_WITH_CREDENTIALS.search(value)
        or _SCHWAB_TOKEN_HINT.search(value)
    )
