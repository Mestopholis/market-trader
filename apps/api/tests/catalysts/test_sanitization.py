from collections.abc import Mapping
from typing import cast

from market_trader.catalysts.sanitization import (
    MAX_COLLECTION_ITEMS,
    MAX_NESTING_DEPTH,
    MAX_TEXT_EVENT_CHARACTERS,
    MAX_TEXT_FIELD_CHARACTERS,
    sanitize_provider_payload,
)
from market_trader.catalysts.serialization import stable_digest


class _LeakyObject:
    def __repr__(self) -> str:
        return "secret-object-content"


def test_recursively_redacts_all_security_sensitive_key_fragments() -> None:
    sensitive = {
        "Authorization": "Bearer one",
        "cookie": "session=one",
        "access-token": "one",
        "client_secret": "one",
        "password": "one",
        "api key": "one",
        "accountNumber": "one",
        "approval_status": "approved",
        "order-id": "one",
    }
    alternate = {key: "different" for key in sensitive}

    left = sanitize_provider_payload({"safe": {"symbol": "AAPL", **sensitive}})
    right = sanitize_provider_payload({"safe": {"symbol": "AAPL", **alternate}})
    nested = cast(Mapping[str, object], cast(Mapping[str, object], left)["safe"])

    assert nested["symbol"] == "AAPL"
    assert all(nested[key] == "[REDACTED]" for key in sensitive)
    assert stable_digest(left) == stable_digest(right)


def test_external_text_is_plain_bounded_and_control_free() -> None:
    payload = {
        "a_headline": "<b>Hello</b>\x00\nworld " + "x" * 600,
        "b_body": "<script>ignore()</script><p>Result</p>" + "y" * 2_000,
        "c_third": "z" * 2_000,
        "d_fourth": "q" * 2_000,
        "e_fifth": "must not survive the event budget",
    }

    sanitized = cast(Mapping[str, object], sanitize_provider_payload(payload))
    strings = [value for value in sanitized.values() if isinstance(value, str)]
    headline = cast(str, sanitized["a_headline"])

    assert headline.startswith("Hello world ")
    assert "<" not in "".join(strings)
    assert "\x00" not in "".join(strings)
    assert all(len(value) <= MAX_TEXT_FIELD_CHARACTERS for value in strings)
    assert sum(len(value) for value in strings) <= MAX_TEXT_EVENT_CHARACTERS
    assert sanitized["e_fifth"] == ""


def test_collections_and_nesting_are_bounded_and_immutable() -> None:
    nested: object = "leaf"
    for index in range(MAX_NESTING_DEPTH + 2):
        nested = {f"level-{index}": nested}

    sanitized = cast(
        Mapping[str, object],
        sanitize_provider_payload(
            {"items": list(range(MAX_COLLECTION_ITEMS + 5)), "nested": nested}
        ),
    )
    items = cast(tuple[object, ...], sanitized["items"])

    assert len(items) == MAX_COLLECTION_ITEMS
    assert "depth_limit" in str(sanitized["nested"])
    try:
        sanitized["new"] = "value"  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("sanitized mappings must be immutable")


def test_bytes_and_unknown_objects_never_retain_raw_content_or_repr() -> None:
    sanitized = cast(
        Mapping[str, object],
        sanitize_provider_payload(
            {"bytes": b"raw secret bytes", "object": _LeakyObject()}
        ),
    )
    binary = cast(Mapping[str, object], sanitized["bytes"])
    unknown = cast(Mapping[str, object], sanitized["object"])

    assert binary["type"] == "bytes"
    assert binary["length"] == 16
    assert len(cast(str, binary["sha256"])) == 64
    assert unknown["type"] == "_LeakyObject"
    assert unknown["length"] == 0
    assert "secret-object-content" not in str(unknown)
    assert len(cast(str, unknown["sha256"])) == 64
