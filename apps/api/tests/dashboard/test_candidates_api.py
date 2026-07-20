from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from market_trader.api.dashboard import get_dashboard_read_model
from market_trader.dashboard.models import (
    CandidateDetail,
    CandidateListItem,
    CandidateListResponse,
    DataState,
    SourceSummary,
    WarningSummary,
)
from market_trader.main import app

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


class FakeCandidateReadModel:
    def __init__(self) -> None:
        self.last_limit: int | None = None
        self.last_cursor: str | None = None

    def candidates(self, *, limit: int, cursor: str | None) -> CandidateListResponse:
        self.last_limit = limit
        self.last_cursor = cursor
        return CandidateListResponse(
            as_of=AS_OF,
            data_state=DataState.PARTIAL,
            candidates=(
                CandidateListItem(
                    candidate_key="candidate:msft:2026-07-20",
                    symbol="MSFT",
                    direction="bearish",
                    strategy="bearish_breakdown",
                    score="74.00",
                    qualification_state="blocked",
                    catalyst_state="unresolved",
                    risk_state="blocked",
                    data_state=DataState.STALE,
                    observed_at=AS_OF,
                    reason_codes=("risk.daily_loss",),
                    source_keys=("scanner:run:2",),
                ),
                CandidateListItem(
                    candidate_key="candidate:aapl:2026-07-20",
                    symbol="AAPL",
                    direction="bullish",
                    strategy="bullish_breakout",
                    score="87.50",
                    qualification_state="qualified",
                    catalyst_state="confirmed",
                    risk_state="warning",
                    data_state=DataState.READY,
                    observed_at=AS_OF,
                    reason_codes=("score.momentum", "catalyst.confirmed"),
                    source_keys=("scanner:run:1", "risk:decision:1"),
                ),
            ),
            next_cursor="cursor:next",
            sources=(
                SourceSummary(
                    name="scanner",
                    state=DataState.STALE,
                    version="scanner-policy-v1",
                    observed_at=AS_OF,
                    stable_key="scanner:latest",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="scanner.stale",
                    severity="warning",
                    message="Scanner data is stale",
                    source_keys=("scanner:latest",),
                ),
            ),
        )

    def candidate_detail(self, candidate_key: str) -> CandidateDetail | None:
        if candidate_key != "candidate:aapl:2026-07-20":
            return None
        return CandidateDetail(
            candidate_key=candidate_key,
            symbol="AAPL",
            data_state=DataState.PARTIAL,
            as_of=AS_OF,
            scanner={
                "score": "87.50",
                "policy_version": "scanner-policy-v1",
                "input_digest": "scanner-input",
                "result_digest": "scanner-result",
            },
            catalysts={
                "decision": "confirmed",
                "policy_version": "catalyst-policy-v1",
                "result_digest": "catalyst-result",
            },
            options={"state": "unavailable"},
            risk={
                "status": "warning",
                "policy_version": "risk-policy-v1",
                "result_digest": "risk-result",
            },
            sources=(
                SourceSummary(
                    name="risk",
                    state=DataState.READY,
                    version="risk-policy-v1",
                    observed_at=AS_OF,
                    stable_key="risk:decision:1",
                ),
                SourceSummary(
                    name="scanner",
                    state=DataState.READY,
                    version="scanner-policy-v1",
                    observed_at=AS_OF,
                    stable_key="scanner:run:1",
                ),
            ),
            warnings=(),
        )


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_dashboard_candidates_returns_sorted_bounded_list() -> None:
    read_model = FakeCandidateReadModel()
    app.dependency_overrides[get_dashboard_read_model] = lambda: read_model

    response = TestClient(app).get("/api/dashboard/candidates?limit=2&cursor=cursor:start")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert read_model.last_limit == 2
    assert read_model.last_cursor == "cursor:start"
    assert body["as_of"] == "2026-07-20T15:30:00Z"
    assert body["data_state"] == "partial"
    assert [candidate["symbol"] for candidate in body["candidates"]] == ["AAPL", "MSFT"]
    assert body["candidates"][0]["reason_codes"] == ["catalyst.confirmed", "score.momentum"]
    assert body["candidates"][1]["data_state"] == "stale"
    assert body["next_cursor"] == "cursor:next"


def test_dashboard_candidates_rejects_invalid_limit_and_cursor() -> None:
    client = TestClient(app)

    assert client.get("/api/dashboard/candidates?limit=0").status_code == 422
    assert client.get("/api/dashboard/candidates?limit=101").status_code == 422
    assert client.get("/api/dashboard/candidates?cursor=bad cursor").status_code == 422


def test_dashboard_candidate_detail_traces_downstream_sections() -> None:
    app.dependency_overrides[get_dashboard_read_model] = lambda: FakeCandidateReadModel()

    response = TestClient(app).get("/api/dashboard/candidates/candidate:aapl:2026-07-20")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["candidate_key"] == "candidate:aapl:2026-07-20"
    assert body["scanner"]["policy_version"] == "scanner-policy-v1"
    assert body["catalysts"]["result_digest"] == "catalyst-result"
    assert body["options"] == {"state": "unavailable"}
    assert body["risk"]["result_digest"] == "risk-result"
    assert [source["name"] for source in body["sources"]] == ["risk", "scanner"]
    assert "order_payload" not in response.text


def test_dashboard_candidate_detail_returns_safe_missing_state() -> None:
    app.dependency_overrides[get_dashboard_read_model] = lambda: FakeCandidateReadModel()

    response = TestClient(app).get("/api/dashboard/candidates/candidate:missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "candidate_not_found"}
