import json

from market_trader.observability.redaction import REDACTED, redact_value


def test_redacts_secret_shaped_keys_recursively() -> None:
    payload = {
        "Authorization": "Bearer should-not-leak",
        "cookie": "session=should-not-leak",
        "csrf-token": "csrf-secret",
        "database_url": "postgresql://user:password@example.test/db",
        "nested": {
            "apiKey": "api-secret",
            "safe": "visible",
            "items": [{"brokerAccountNumber": "123456789"}],
        },
    }

    redacted = redact_value(payload)

    assert redacted == {
        "Authorization": REDACTED,
        "cookie": REDACTED,
        "csrf-token": REDACTED,
        "database_url": REDACTED,
        "nested": {
            "apiKey": REDACTED,
            "items": [{"brokerAccountNumber": REDACTED}],
            "safe": "visible",
        },
    }
    serialized = json.dumps(redacted)
    assert "should-not-leak" not in serialized
    assert "password@example" not in serialized
    assert "123456789" not in serialized


def test_redacts_secret_shaped_strings_inside_safe_keys() -> None:
    payload = {
        "message": "Authorization: Bearer abc.def.ghi failed",
        "dsn": "sqlite:///local.db",
        "remote": "postgresql://user:secret@example.test/db",
        "token_hint": "xoxb-123456789012-secret",
    }

    redacted = redact_value(payload)

    assert isinstance(redacted, dict)
    assert redacted["message"] == "Authorization: [REDACTED] failed"
    assert redacted["dsn"] == "sqlite:///local.db"
    assert redacted["remote"] == REDACTED
    assert redacted["token_hint"] == REDACTED


def test_bounds_collections_and_unknown_values_without_raw_repr() -> None:
    class SensitiveObject:
        def __repr__(self) -> str:
            return "SensitiveObject(password=secret)"

    redacted = redact_value({"values": list(range(105)), "object": SensitiveObject()})

    assert isinstance(redacted, dict)
    values = redacted["values"]
    assert isinstance(values, list)
    assert values == list(range(100))
    assert redacted["object"] == {"type": "SensitiveObject"}
    assert "secret" not in json.dumps(redacted)
