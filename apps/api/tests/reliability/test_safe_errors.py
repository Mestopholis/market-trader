import json
import logging
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_trader.main import create_app
from market_trader.observability.correlation import CORRELATION_ID_HEADER, REQUEST_ID_HEADER
from market_trader.observability.logging import LOGGER_NAME


def test_unhandled_exception_returns_safe_redacted_error() -> None:
    app = create_app()
    _add_boom_route(app)
    records = _capture_observability_records()

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/boom",
        headers={CORRELATION_ID_HEADER: "corr-safe-error"},
    )

    assert response.status_code == 500
    assert response.headers[CORRELATION_ID_HEADER] == "corr-safe-error"
    assert response.headers[REQUEST_ID_HEADER].startswith("req_")
    body = response.json()
    assert body == {
        "code": "internal_error",
        "summary": "An internal error occurred.",
        "correlation_id": "corr-safe-error",
        "remediation": "Use the correlation id to inspect local structured logs.",
    }
    serialized = response.text
    assert "postgresql://" not in serialized
    assert "Bearer" not in serialized
    assert "secret" not in serialized
    payload = _single_error_log(records)
    assert payload["event"] == "api.request.failed"
    assert payload["component"] == "api"
    assert payload["error_code"] == "internal_error"
    assert payload["correlation_id"] == "corr-safe-error"
    assert "postgresql://" not in json.dumps(payload)
    assert "Bearer" not in json.dumps(payload)
    assert "secret" not in json.dumps(payload)


def _add_boom_route(app: FastAPI) -> None:
    @app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError(
            "failed for postgresql://user:secret@example.test/db "
            "Authorization: Bearer abcdefghijklmnop"
        )


def _capture_observability_records() -> list[logging.LogRecord]:
    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logging.disable(logging.NOTSET)
    logger = logging.getLogger(LOGGER_NAME)
    logger.disabled = False
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.addHandler(ListHandler())
    return records


def _single_error_log(records: list[logging.LogRecord]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for record in records:
        if record.name == LOGGER_NAME and '"event":"api.request.failed"' in record.getMessage():
            loaded = json.loads(record.getMessage())
            assert isinstance(loaded, dict)
            matches.append(cast(dict[str, Any], loaded))
    assert len(matches) == 1
    return matches[0]
