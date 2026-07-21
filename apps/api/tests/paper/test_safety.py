from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import FillORM, OrderORM, ProposedTradeORM
from market_trader.domain.time import FrozenClock
from market_trader.main import app
from market_trader.paper.models import (
    ApprovalCard,
    ApprovalCardState,
    PaperAction,
    PaperBrokerScenario,
)
from market_trader.paper.service import PaperLifecycleService
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
FORBIDDEN_TERMS = ("schwab", "live_mode", "api_key", "secret", "password")
OPENAPI_FORBIDDEN_TERMS = ("schwab", "live_mode", "api_key", "secret")


def test_paper_api_openapi_excludes_live_broker_and_credential_contracts() -> None:
    openapi = TestClient(app).get("/api/openapi.json").text.lower()

    for forbidden in (*OPENAPI_FORBIDDEN_TERMS, "broker_reference"):
        assert forbidden not in openapi


def test_paper_lifecycle_persists_only_simulated_references(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            service = PaperLifecycleService(session, clock=FrozenClock(AS_OF))
            approval = service.approve_card(_card())
            preview = service.preview_approval(approval.id)
            submitted = service.submit_approval(
                approval.id,
                preview_digest=preview.preview_digest,
                scenario=PaperBrokerScenario.FULL_FILL,
            )
            session.commit()

        with Session(engine) as session:
            orders = session.scalars(select(OrderORM)).all()
            fills = session.scalars(select(FillORM)).all()
            proposed_trades = session.scalars(select(ProposedTradeORM)).all()

        assert submitted.order.broker_reference is None
        assert orders
        assert fills
        assert all(order.broker_reference is None for order in orders)
        assert all(order.simulated_broker_reference for order in orders)
        assert all(fill.broker_reference is None for fill in fills)
        assert all(fill.simulated_broker_reference for fill in fills)
        for proposed in proposed_trades:
            _assert_payload_safe(proposed.order_intent_payload)
        for order in orders:
            _assert_payload_safe(order.order_intent_payload)
        for fill in fills:
            _assert_payload_safe(fill.payload)
    finally:
        engine.dispose()


def _assert_payload_safe(value: object) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        assert all(term not in lowered for term in FORBIDDEN_TERMS)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            assert all(term not in lowered_key for term in FORBIDDEN_TERMS)
            if lowered_key != "simulated_broker_reference":
                assert "broker_reference" not in lowered_key
            _assert_payload_safe(item)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _assert_payload_safe(item)


def _card(*, candidate_key: str = "candidate-a") -> ApprovalCard:
    return ApprovalCard(
        card_key=f"card-{candidate_key}",
        state=ApprovalCardState.READY,
        candidate_key=candidate_key,
        symbol="MSFT",
        direction="long",
        proposal_kind="single",
        quantity=2,
        limit_price=Decimal("1.25"),
        maximum_loss=Decimal("250.00"),
        risk_decision_key=f"risk-{candidate_key}",
        risk_status="approved",
        risk_input_digest=f"risk-input-{candidate_key}",
        risk_result_digest=f"risk-result-{candidate_key}",
        source_keys=(f"candidate:{candidate_key}", f"risk_decision:risk-{candidate_key}"),
        allowed_actions=(PaperAction.APPROVE, PaperAction.MODIFY, PaperAction.REJECT),
        expires_at=AS_OF + timedelta(minutes=5),
        as_of=AS_OF,
    )
