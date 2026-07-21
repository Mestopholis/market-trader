from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from market_trader.api.auth import require_authenticated_session
from market_trader.config import get_settings
from market_trader.db.migrations import alembic_config
from market_trader.main import create_app
from market_trader.observability.correlation import CORRELATION_ID_HEADER, REQUEST_ID_HEADER
from market_trader.security.session import SessionClaims


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_readiness_api_returns_redacted_component_state(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'readiness.db'}"
    command.upgrade(alembic_config(database_url), "head")
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", database_url)
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    response = TestClient(app).get(
        "/api/readiness",
        headers={CORRELATION_ID_HEADER: "corr-readiness"},
    )

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER] == "corr-readiness"
    assert response.headers[REQUEST_ID_HEADER].startswith("req_")
    body = response.json()
    assert body["trading_mode"] == "paper"
    assert body["status"] == "ok"
    assert body["blocking"] is False
    assert {component["name"] for component in body["components"]} >= {
        "database",
        "migrations",
        "backup",
        "market_data_freshness",
        "scheduler_jobs",
        "risk_locks",
        "paper_reconciliation",
        "auth_config",
        "security_scan",
    }
    assert database_url not in response.text
    assert "database_url" not in response.text
