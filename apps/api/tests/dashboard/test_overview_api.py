from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from market_trader.api.dashboard import get_dashboard_read_model
from market_trader.dashboard.models import (
    DashboardOverview,
    DataState,
    SourceSummary,
    WarningSummary,
)
from market_trader.main import app
from tests.auth_helpers import authenticated_client

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


class FakeDashboardReadModel:
    def __init__(self, overview: DashboardOverview) -> None:
        self.overview_calls = 0
        self._overview = overview

    def overview(self) -> DashboardOverview:
        self.overview_calls += 1
        return self._overview


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_dashboard_overview_returns_read_only_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    read_model = FakeDashboardReadModel(
        DashboardOverview(
            as_of=AS_OF,
            data_state=DataState.PARTIAL,
            paper_mode=True,
            market_state="entry_open",
            entry_allowed=True,
            sources=(
                SourceSummary(
                    name="scanner",
                    state=DataState.STALE,
                    version="scanner-policy-v1",
                    observed_at=AS_OF,
                    stable_key="scanner:run:latest",
                ),
                SourceSummary(
                    name="risk",
                    state=DataState.READY,
                    version="risk-policy-v1",
                    observed_at=AS_OF,
                    stable_key="risk:decision:latest",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="scanner.stale",
                    severity="warning",
                    message="Scanner data is stale",
                    source_keys=("scanner:run:latest",),
                ),
            ),
        )
    )
    app.dependency_overrides[get_dashboard_read_model] = lambda: read_model

    response = authenticated_client(monkeypatch, app).get("/api/dashboard/overview")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "as_of": "2026-07-20T15:30:00Z",
        "data_state": "partial",
        "paper_mode": True,
        "market_state": "entry_open",
        "entry_allowed": True,
        "sources": [
            {
                "name": "risk",
                "state": "ready",
                "version": "risk-policy-v1",
                "observed_at": "2026-07-20T15:30:00Z",
                "stable_key": "risk:decision:latest",
                "digest": None,
            },
            {
                "name": "scanner",
                "state": "stale",
                "version": "scanner-policy-v1",
                "observed_at": "2026-07-20T15:30:00Z",
                "stable_key": "scanner:run:latest",
                "digest": None,
            },
        ],
        "warnings": [
            {
                "code": "scanner.stale",
                "severity": "warning",
                "message": "Scanner data is stale",
                "source_keys": ["scanner:run:latest"],
            }
        ],
    }
    assert read_model.overview_calls == 1


def test_dashboard_overview_default_empty_state_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    response = authenticated_client(monkeypatch, app).get("/api/dashboard/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["paper_mode"] is True
    assert body["data_state"] in {"partial", "unavailable"}
    assert body["sources"]
    assert "database_url" not in response.text
    assert "sqlite:///" not in response.text


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_dashboard_overview_rejects_write_methods(method: str) -> None:
    client = TestClient(app)

    response = getattr(client, method)("/api/dashboard/overview")

    assert response.status_code in {404, 405}
