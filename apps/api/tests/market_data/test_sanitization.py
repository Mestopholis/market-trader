from datetime import UTC, date, datetime
from decimal import Decimal

from market_trader.market_data.sanitization import (
    canonical_digest,
    canonical_json,
    ingestion_key,
    sanitize_payload,
)


def test_sanitizes_nested_secrets_before_canonical_digest() -> None:
    left = {
        "symbol": "SPY",
        "Authorization": "Bearer secret",
        "nested": {"cookie": "x", "api-key": "abc"},
    }
    right = {
        "nested": {"api-key": "different", "cookie": "other"},
        "Authorization": "other",
        "symbol": "SPY",
    }

    sanitized_left = sanitize_payload(left)
    sanitized_right = sanitize_payload(right)

    assert sanitized_left["Authorization"] == "[REDACTED]"
    assert sanitized_left["nested"] == {"cookie": "[REDACTED]", "api-key": "[REDACTED]"}
    assert canonical_digest(sanitized_left) == canonical_digest(sanitized_right)


def test_canonical_json_is_independent_of_mapping_insertion_order() -> None:
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert canonical_digest({"b": 2, "a": 1}) == canonical_digest({"a": 1, "b": 2})


def test_sanitizes_exact_types_without_binary_floats() -> None:
    payload = {
        "price": Decimal("625.10"),
        "day": date(2026, 7, 17),
        "observed": datetime(2026, 7, 17, 14, 30, tzinfo=UTC),
    }

    assert sanitize_payload(payload) == {
        "price": "625.10",
        "day": "2026-07-17",
        "observed": "2026-07-17T14:30:00+00:00",
    }


def test_bounds_strings_and_collections() -> None:
    sanitized = sanitize_payload({"long": "x" * 3000, "items": list(range(1005))})

    assert sanitized["long"] == "x" * 2048
    assert len(sanitized["items"]) == 1000


def test_binary_and_unknown_values_are_replaced_with_metadata() -> None:
    binary = sanitize_payload({"value": b"secret bytes"})["value"]
    unknown = sanitize_payload({"value": object()})["value"]

    assert binary["type"] == "bytes"
    assert binary["length"] == 12
    assert len(binary["sha256"]) == 64
    assert unknown["type"] == "object"
    assert len(unknown["sha256"]) == 64


def test_ingestion_key_is_stable_source_scoped_and_schema_scoped() -> None:
    assert ingestion_key("fixture", "event-1", 1) == ingestion_key("fixture", "event-1", 1)
    assert ingestion_key("fixture", "event-1", 1) != ingestion_key("other", "event-1", 1)
    assert ingestion_key("fixture", "event-1", 1) != ingestion_key("fixture", "event-1", 2)
