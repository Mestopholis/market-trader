from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from market_trader.api.dashboard import get_dashboard_read_model
from market_trader.dashboard.models import (
    AnalyticsSummary,
    DataState,
    JournalEventListResponse,
    JournalEventSummary,
    RiskSummary,
    SourceSummary,
    WarningSummary,
)
from market_trader.main import app

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


class FakeRiskJournalAnalyticsReadModel:
    def __init__(self) -> None:
        self.journal_limit: int | None = None
        self.journal_cursor: str | None = None
        self.journal_event_type: str | None = None
        self.journal_correlation_id: str | None = None

    def risk(self) -> RiskSummary:
        return RiskSummary(
            as_of=AS_OF,
            data_state=DataState.PARTIAL,
            latest_decision_key="risk:decision:1",
            status="blocked",
            checks=(
                WarningSummary(
                    code="daily_loss",
                    severity="block",
                    message="Daily loss lock is active",
                    source_keys=("lock:1",),
                ),
            ),
            active_locks=("manual_operator_hold", "daily_loss"),
            tax_disclaimer="Informational estimate only; not tax advice.",
            sources=(
                SourceSummary(
                    name="risk",
                    state=DataState.READY,
                    version="risk-policy-v1",
                    observed_at=AS_OF,
                    stable_key="risk:decision:1",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="tax.estimate",
                    severity="warning",
                    message="Tax warning is informational only",
                    source_keys=("tax:lot:1",),
                ),
            ),
        )

    def journal(
        self,
        *,
        limit: int,
        cursor: str | None,
        event_type: str | None,
        correlation_id: str | None,
    ) -> JournalEventListResponse:
        self.journal_limit = limit
        self.journal_cursor = cursor
        self.journal_event_type = event_type
        self.journal_correlation_id = correlation_id
        return JournalEventListResponse(
            as_of=AS_OF,
            data_state=DataState.READY,
            events=(
                JournalEventSummary(
                    event_key="journal:2",
                    event_type="risk_decision.recorded",
                    occurred_at=AS_OF,
                    correlation_id="corr:1",
                    actor="system",
                    source_key="risk:decision:1",
                    payload_summary={"status": "blocked"},
                ),
                JournalEventSummary(
                    event_key="journal:1",
                    event_type="scanner_run.recorded",
                    occurred_at=AS_OF,
                    correlation_id="corr:1",
                    actor="system",
                    source_key="scanner:run:1",
                    payload_summary={"qualified": 3},
                ),
            ),
            next_cursor="journal:next",
            sources=(),
            warnings=(),
        )

    def analytics(self) -> AnalyticsSummary:
        return AnalyticsSummary(
            as_of=AS_OF,
            data_state=DataState.READY,
            candidate_counts={"qualified": 3, "blocked": 2},
            strategy_mix={"bullish_breakout": 2, "bearish_breakdown": 1},
            block_reasons={"daily_loss": 1, "stale_data": 1},
            stale_counts={"scanner": 1},
            risk_status_distribution={"blocked": 2, "warning": 1},
            sources=(
                SourceSummary(
                    name="analytics",
                    state=DataState.READY,
                    version="dashboard-analytics-v1",
                    observed_at=AS_OF,
                    stable_key="analytics:local",
                ),
            ),
            warnings=(),
        )


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_dashboard_risk_returns_checks_locks_and_tax_disclaimer() -> None:
    app.dependency_overrides[get_dashboard_read_model] = lambda: FakeRiskJournalAnalyticsReadModel()

    response = TestClient(app).get("/api/dashboard/risk")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["latest_decision_key"] == "risk:decision:1"
    assert body["status"] == "blocked"
    assert body["checks"][0]["code"] == "daily_loss"
    assert body["active_locks"] == ["daily_loss", "manual_operator_hold"]
    assert body["tax_disclaimer"] == "Informational estimate only; not tax advice."
    assert "order_payload" not in response.text


def test_dashboard_journal_supports_filters_and_redacted_bounded_events() -> None:
    read_model = FakeRiskJournalAnalyticsReadModel()
    app.dependency_overrides[get_dashboard_read_model] = lambda: read_model

    response = TestClient(app).get(
        "/api/dashboard/journal"
        "?limit=2&cursor=journal:start"
        "&event_type=risk_decision.recorded&correlation_id=corr:1"
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert read_model.journal_limit == 2
    assert read_model.journal_cursor == "journal:start"
    assert read_model.journal_event_type == "risk_decision.recorded"
    assert read_model.journal_correlation_id == "corr:1"
    assert [event["event_key"] for event in body["events"]] == ["journal:1", "journal:2"]
    assert body["next_cursor"] == "journal:next"
    assert "token" not in response.text
    assert "secret" not in response.text


def test_dashboard_journal_rejects_invalid_pagination_and_filters() -> None:
    client = TestClient(app)

    assert client.get("/api/dashboard/journal?limit=0").status_code == 422
    assert client.get("/api/dashboard/journal?limit=101").status_code == 422
    assert client.get("/api/dashboard/journal?cursor=bad cursor").status_code == 422
    assert client.get("/api/dashboard/journal?event_type=bad event").status_code == 422


def test_dashboard_analytics_returns_local_deterministic_counts() -> None:
    app.dependency_overrides[get_dashboard_read_model] = lambda: FakeRiskJournalAnalyticsReadModel()

    response = TestClient(app).get("/api/dashboard/analytics")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["candidate_counts"] == {"blocked": 2, "qualified": 3}
    assert body["strategy_mix"]["bullish_breakout"] == 2
    assert body["block_reasons"] == {"daily_loss": 1, "stale_data": 1}
    assert body["stale_counts"] == {"scanner": 1}
    assert body["risk_status_distribution"] == {"blocked": 2, "warning": 1}


@pytest.mark.parametrize(
    "path",
    ["/api/dashboard/risk", "/api/dashboard/journal", "/api/dashboard/analytics"],
)
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_dashboard_summary_routes_reject_write_methods(path: str, method: str) -> None:
    client = TestClient(app)

    response = getattr(client, method)(path)

    assert response.status_code in {404, 405}
