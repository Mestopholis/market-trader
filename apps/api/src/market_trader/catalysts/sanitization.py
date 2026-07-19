import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from types import MappingProxyType

MAX_TEXT_FIELD_CHARACTERS = 512
MAX_TEXT_EVENT_CHARACTERS = 2_048
MAX_COLLECTION_ITEMS = 100
MAX_NESTING_DEPTH = 8

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
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")

type SanitizedProviderValue = (
    None
    | bool
    | int
    | str
    | tuple[SanitizedProviderValue, ...]
    | Mapping[str, SanitizedProviderValue]
)


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


@dataclass
class _Budget:
    remaining: int = MAX_TEXT_EVENT_CHARACTERS


def sanitize_provider_payload(value: object) -> SanitizedProviderValue:
    return _sanitize(value, depth=0, budget=_Budget())


def _sanitize(value: object, *, depth: int, budget: _Budget) -> SanitizedProviderValue:
    if depth > MAX_NESTING_DEPTH:
        return _metadata("depth_limit", 0)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value, budget)
    if isinstance(value, Decimal):
        return _sanitize_text(str(value), budget)
    if isinstance(value, (datetime, date)):
        return _sanitize_text(value.isoformat(), budget)
    if isinstance(value, bytes):
        return _metadata("bytes", len(value), digest=value)
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, depth=depth, budget=budget)
    if isinstance(value, (list, tuple)):
        return tuple(
            _sanitize(item, depth=depth + 1, budget=budget)
            for item in value[:MAX_COLLECTION_ITEMS]
        )
    type_name = type(value).__name__[:MAX_TEXT_FIELD_CHARACTERS]
    return _metadata(type_name, 0)


def _sanitize_mapping(
    value: Mapping[object, object],
    *,
    depth: int,
    budget: _Budget,
) -> Mapping[str, SanitizedProviderValue]:
    keyed = sorted((str(key)[:MAX_TEXT_FIELD_CHARACTERS], item) for key, item in value.items())
    sanitized: dict[str, SanitizedProviderValue] = {}
    for key, item in keyed[:MAX_COLLECTION_ITEMS]:
        sanitized[key] = (
            "[REDACTED]"
            if _is_sensitive_key(key)
            else _sanitize(item, depth=depth + 1, budget=budget)
        )
    return MappingProxyType(sanitized)


def _sanitize_text(value: str, budget: _Budget) -> str:
    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    plain = _WHITESPACE.sub(" ", _CONTROL_CHARACTERS.sub("", "".join(parser.parts))).strip()
    available = min(MAX_TEXT_FIELD_CHARACTERS, budget.remaining)
    bounded = plain[:available]
    budget.remaining -= len(bounded)
    return bounded


def _metadata(
    type_name: str,
    length: int,
    *,
    digest: bytes | None = None,
) -> Mapping[str, SanitizedProviderValue]:
    digest_input = digest if digest is not None else type_name.encode("utf-8")
    return MappingProxyType(
        {
            "type": type_name,
            "length": length,
            "sha256": hashlib.sha256(digest_input).hexdigest(),
        }
    )


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(" ", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)
