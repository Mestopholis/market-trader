from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from market_trader.api.auth import require_authenticated_session, require_csrf_protection
from market_trader.api.paper import get_paper_lifecycle_service
from market_trader.main import app
from market_trader.paper.models import (
    ApprovalCard,
    ApprovalCardState,
    PaperAction,
    PaperBrokerScenario,
    PaperOrderStatus,
    PaperPreview,
)
from market_trader.paper.service import PaperLifecycleError
from market_trader.security.session import SessionClaims

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_paper_routes_return_no_store_and_paper_mode_fields() -> None:
    fake = FakePaperService()
    app.dependency_overrides[get_paper_lifecycle_service] = lambda: fake
    client = _authorized_client()

    cards = client.get("/api/paper/approval-cards")
    approved = client.post("/api/paper/approval-cards/card-a/approve")
    preview = client.post(f"/api/paper/approvals/{approved.json()['id']}/preview")
    submitted = client.post(
        f"/api/paper/approvals/{approved.json()['id']}/submit",
        json={"preview_digest": preview.json()["preview_digest"], "scenario": "full_fill"},
    )
    orders = client.get("/api/paper/orders")
    positions = client.get("/api/paper/positions")
    recovery = client.post("/api/paper/recover")

    assert cards.headers["cache-control"] == "no-store"
    assert cards.json()["paper_mode"] is True
    assert cards.json()["approval_cards"][0]["card_key"] == "card-a"
    assert approved.json()["paper_mode"] is True
    assert preview.json()["paper_mode"] is True
    assert submitted.json()["order"]["broker_reference"] is None
    assert orders.json()["orders"]
    assert positions.json()["positions"]
    assert recovery.json()["open_positions"]


def test_paper_action_routes_and_validation_errors() -> None:
    fake = FakePaperService()
    app.dependency_overrides[get_paper_lifecycle_service] = lambda: fake
    client = _authorized_client()

    modified = client.post(
        "/api/paper/approval-cards/card-a/modify",
        json={"quantity": 1, "limit_price": "1.15"},
    )
    rejected = client.post("/api/paper/approval-cards/card-a/reject")
    canceled = client.post("/api/paper/orders/order-a/cancel")
    replaced = client.post("/api/paper/orders/order-a/replace", json={"limit_price": "1.10"})
    bad_payload = client.post(
        "/api/paper/approval-cards/card-a/modify",
        json={"quantity": 1, "limit_price": "1.15", "live_mode": True},
    )
    fake.error = PaperLifecycleError("stale_preview")
    stale = client.post(
        "/api/paper/approvals/approval-a/submit",
        json={"preview_digest": "old", "scenario": "full_fill"},
    )

    assert modified.json()["decision_payload"]["intent"]["quantity"] == 1
    assert rejected.json()["status"] == "rejected"
    assert canceled.json()["status"] == "canceled"
    assert replaced.json()["status"] == "replaced"
    assert bad_payload.status_code == 422
    assert stale.status_code == 409
    assert stale.json()["detail"] == "stale_preview"


def _authorized_client() -> TestClient:
    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=AS_OF,
    )
    app.dependency_overrides[require_csrf_protection] = lambda: None
    return TestClient(app)


def test_paper_openapi_excludes_live_and_external_broker_contracts() -> None:
    payload = TestClient(app).get("/api/openapi.json").text.lower()

    assert "live_mode" not in payload
    assert "schwab" not in payload
    assert "api_key" not in payload
    assert "broker_reference" not in payload


class FakePaperService:
    def __init__(self) -> None:
        self.error: PaperLifecycleError | None = None

    def approval_cards(self) -> tuple[ApprovalCard, ...]:
        return (_card(),)

    def approve_card(self, _card: ApprovalCard) -> SimpleNamespace:
        return _approval("approved")

    def modify_card(
        self, _card: ApprovalCard, *, quantity: int, limit_price: Decimal
    ) -> SimpleNamespace:
        approval = _approval("approved")
        approval.decision_payload["intent"]["quantity"] = quantity
        approval.decision_payload["intent"]["limit_price"] = str(limit_price)
        return approval

    def reject_card(self, _card: ApprovalCard) -> SimpleNamespace:
        return _approval("rejected")

    def preview_approval(self, _approval_id: str) -> PaperPreview:
        return _preview()

    def submit_approval(
        self,
        _approval_id: str,
        *,
        preview_digest: str,
        scenario: PaperBrokerScenario = PaperBrokerScenario.FULL_FILL,
    ) -> object:
        if self.error is not None:
            raise self.error
        return {
            "order": {
                "order_id": "order-a",
                "status": PaperOrderStatus.FILLED,
                "simulated_broker_reference": "sim-order-a",
                "broker_reference": None,
            },
            "persisted_order_id": "persisted-order-a",
            "position": {"position_key": "position-a", "status": "open"},
            "paper_mode": True,
        }

    def cancel_order(self, _order_id: str) -> object:
        return {"id": "order-a", "status": "canceled", "paper_mode": True}

    def replace_order(self, _order_id: str, *, limit_price: Decimal) -> object:
        return {"id": "order-a", "status": "replaced", "limit_price": str(limit_price)}

    def recover(self) -> object:
        return {
            "open_orders": [{"id": "order-a", "status": "working"}],
            "open_positions": [{"id": "position-a", "status": "open"}],
        }


def _approval(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="approval-a",
        status=status,
        decision_payload={"intent": {"quantity": 2, "limit_price": "1.25"}},
        broker_reference=None,
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


def _preview() -> PaperPreview:
    return PaperPreview(
        preview_key="preview-a",
        approval_id="approval-a",
        intent_key="intent-a",
        quote_observed_at=AS_OF,
        quote_expires_at=AS_OF + timedelta(minutes=1),
        bid=Decimal("1.10"),
        ask=Decimal("1.30"),
        limit_price=Decimal("1.25"),
        estimated_maximum_loss=Decimal("250.00"),
        reserved_risk=Decimal("250.00"),
        warnings=(),
        preview_digest="preview-digest-a",
        source_keys=("approval:approval-a",),
        as_of=AS_OF,
    )
