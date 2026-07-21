from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from market_trader.api.paper import get_paper_lifecycle_service
from market_trader.dashboard.models import DataState
from market_trader.main import app
from market_trader.paper.models import ApprovalCard, ApprovalCardState, PaperAction
from market_trader.paper.service import PaperLifecycleError, PaperLifecycleService
from market_trader.system_state.blocking import BlockingStatePolicy, SystemBlockedError
from market_trader.system_state.models import ComponentState, SystemReadiness
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("component", "code"),
    [
        ("market_data_freshness", "stale_market_data"),
        ("provider", "provider_unavailable"),
        ("risk_locks", "required_risk_lock_active"),
        ("paper_reconciliation", "paper_reconciliation_failed"),
        ("backup", "backup_integrity_failed"),
        ("restart_recovery", "restart_recovery_gap"),
    ],
)
def test_blocking_policy_raises_stable_failure_codes(component: str, code: str) -> None:
    policy = BlockingStatePolicy(lambda: _readiness(component, code))

    with pytest.raises(SystemBlockedError) as error:
        policy.ensure_paper_mutation_allowed()

    assert error.value.code == code
    assert error.value.component == component


def test_paper_service_blocks_mutations_when_system_state_blocks(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            service = PaperLifecycleService(
                session,
                blocking_policy=BlockingStatePolicy(
                    lambda: _readiness("market_data_freshness", "stale_market_data")
                ),
            )

            with pytest.raises(PaperLifecycleError, match="stale_market_data"):
                service.approve_card(_card())
    finally:
        engine.dispose()


def test_paper_mutation_routes_return_safe_blocked_response() -> None:
    app.dependency_overrides[get_paper_lifecycle_service] = lambda: BlockingFakePaperService(
        expose_card=True
    )

    response = TestClient(app).post("/api/paper/approval-cards/card-a/approve")

    assert response.status_code == 423
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == {
        "paper_mode": True,
        "code": "backup_integrity_failed",
        "component": "backup",
        "summary": "Paper action is blocked by system readiness state.",
    }
    assert "database_url" not in response.text


def test_read_only_paper_and_dashboard_routes_still_render_when_state_blocks() -> None:
    fake = BlockingFakePaperService(expose_card=False)
    app.dependency_overrides[get_paper_lifecycle_service] = lambda: fake
    client = TestClient(app)

    cards = client.get("/api/paper/approval-cards")
    overview = client.get("/api/dashboard/overview")

    assert cards.status_code == 200
    assert cards.json()["paper_mode"] is True
    assert cards.json()["approval_cards"] == []
    assert overview.status_code == 200
    assert overview.json()["paper_mode"] is True
    assert overview.json()["data_state"] in {DataState.PARTIAL.value, DataState.UNAVAILABLE.value}


class BlockingFakePaperService:
    def __init__(self, *, expose_card: bool) -> None:
        self._expose_card = expose_card

    def approval_cards(self) -> tuple[ApprovalCard, ...]:
        return (_card(),) if self._expose_card else ()

    def approve_card(self, _card: ApprovalCard) -> object:
        raise SystemBlockedError("backup_integrity_failed", component="backup")


def _readiness(component: str, code: str) -> SystemReadiness:
    return SystemReadiness(
        status="blocking",
        blocking=True,
        components=[
            ComponentState(
                name=component,
                status="blocking",
                code=code,
                summary="blocked",
                blocking=True,
            )
        ],
    )


def _card() -> ApprovalCard:
    return ApprovalCard(
        card_key="card-a",
        state=ApprovalCardState.READY,
        candidate_key="candidate-a",
        symbol="MSFT",
        direction="long",
        proposal_kind="single",
        quantity=2,
        limit_price=Decimal("1.25"),
        maximum_loss=Decimal("250.00"),
        risk_decision_key="risk-a",
        risk_status="approved",
        risk_input_digest="risk-input-a",
        risk_result_digest="risk-result-a",
        source_keys=("candidate:candidate-a", "risk_decision:risk-a"),
        allowed_actions=(PaperAction.APPROVE, PaperAction.MODIFY, PaperAction.REJECT),
        expires_at=AS_OF + timedelta(minutes=5),
        as_of=AS_OF,
    )
