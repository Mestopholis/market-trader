import json
import logging
from typing import Any, cast

from fastapi.testclient import TestClient

from market_trader.main import create_app
from market_trader.observability.correlation import CORRELATION_ID_HEADER, REQUEST_ID_HEADER
from market_trader.observability.logging import LOGGER_NAME


def test_api_request_emits_structured_log_and_correlation_headers() -> None:
    app = create_app()
    records = _capture_observability_records()

    response = TestClient(app).get("/api/health", headers={CORRELATION_ID_HEADER: "corr-test"})

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER] == "corr-test"
    assert response.headers[REQUEST_ID_HEADER].startswith("req_")
    payload = _single_request_log(records)
    assert payload["event"] == "api.request.completed"
    assert payload["component"] == "api"
    assert payload["method"] == "GET"
    assert payload["path_template"] == "/api/health"
    assert payload["status_code"] == 200
    assert payload["correlation_id"] == "corr-test"
    assert payload["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert isinstance(payload["latency_ms"], int | float)
    assert payload["latency_ms"] >= 0
    assert "timestamp" in payload


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


def _single_request_log(records: list[logging.LogRecord]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for record in records:
        if (
            record.name == LOGGER_NAME
            and '"event":"api.request.completed"' in record.getMessage()
        ):
            loaded = json.loads(record.getMessage())
            assert isinstance(loaded, dict)
            matches.append(cast(dict[str, Any], loaded))
    assert len(matches) == 1
    return matches[0]
