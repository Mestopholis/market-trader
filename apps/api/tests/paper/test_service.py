from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from market_trader.db.models import ApprovalORM, RiskLockORM
from market_trader.domain.time import FrozenClock
from market_trader.paper.models import (
    ApprovalCard,
    ApprovalCardState,
    PaperAction,
    PaperBrokerScenario,
    PaperOrderStatus,
    PaperPositionStatus,
)
from market_trader.paper.service import PaperLifecycleError, PaperLifecycleService
from market_trader.repositories.orders import TradeLifecycleRepository
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def test_approve_preview_submit_and_recover_paper_order(tmp_path: Path) -> None:
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
            recovery = service.recover()
            session.commit()

            order = TradeLifecycleRepository(session).get_order(submitted.persisted_order_id)

        assert approval.status == "approved"
        assert preview.approval_id == approval.id
        assert submitted.order.status is PaperOrderStatus.FILLED
        assert submitted.order.broker_reference is None
        assert submitted.order.simulated_broker_reference.startswith("sim-paper-order-")
        assert submitted.position is not None
        assert submitted.position.status is PaperPositionStatus.OPEN
        assert recovery.open_orders == ()
        assert recovery.open_positions
        assert order is not None
        assert order.broker_reference is None
        assert order.simulated_broker_reference == submitted.order.simulated_broker_reference
    finally:
        engine.dispose()


def test_modify_reject_cancel_and_replace_workflows(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            service = PaperLifecycleService(session, clock=FrozenClock(AS_OF))

            modified = service.modify_card(_card(), quantity=1, limit_price=Decimal("1.15"))
            rejected = service.reject_card(_card(candidate_key="candidate-b"))
            preview = service.preview_approval(modified.id)
            submitted = service.submit_approval(
                modified.id,
                preview_digest=preview.preview_digest,
                scenario=PaperBrokerScenario.ACCEPTED_UNFILLED,
            )
            canceled = service.cancel_order(submitted.order.order_id)
            replacement = service.replace_order(
                submitted.order.order_id,
                limit_price=Decimal("1.10"),
            )
            session.commit()

        assert modified.status == "approved"
        assert modified.decision_payload["intent"]["quantity"] == 1
        assert modified.decision_payload["intent"]["limit_price"] == "1.15"
        assert rejected.status == "rejected"
        assert canceled.status == "canceled"
        assert replacement.status == "replaced"
    finally:
        engine.dispose()


def test_service_blocks_unsafe_or_stale_workflows(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            service = PaperLifecycleService(session, clock=FrozenClock(AS_OF))
            expired_service = PaperLifecycleService(
                session,
                clock=FrozenClock(AS_OF + timedelta(minutes=10)),
            )
            closed_service = PaperLifecycleService(
                session,
                clock=FrozenClock(AS_OF),
                entry_window_open=False,
            )

            with pytest.raises(PaperLifecycleError, match="approval_expired"):
                expired_service.approve_card(_card())

            with pytest.raises(PaperLifecycleError, match="active_risk_lock"):
                session.add(
                    RiskLockORM(
                        id="lock-a",
                        lock_type="daily_loss",
                        status="active",
                        reason="daily loss",
                        source_event_id=None,
                        activated_at=AS_OF,
                        cleared_at=None,
                        clearing_event_id=None,
                        payload={},
                        payload_schema_version=1,
                        correlation_id="corr-lock",
                    )
                )
                session.flush()
                service.approve_card(_card(candidate_key="candidate-lock"))

            session.rollback()
            approval = service.approve_card(_card())
            preview = service.preview_approval(approval.id)
            stored_approval = session.get(ApprovalORM, approval.id)
            assert stored_approval is not None
            changed_payload = dict(stored_approval.decision_payload)
            changed_card = dict(changed_payload["card"])
            changed_card["risk_result_digest"] = "changed-risk"
            changed_payload["card"] = changed_card
            stored_approval.decision_payload = changed_payload
            session.flush()
            with pytest.raises(PaperLifecycleError, match="risk_digest_changed"):
                service.submit_approval(approval.id, preview_digest=preview.preview_digest)

            fresh_approval = service.approve_card(_card(candidate_key="candidate-c"))
            fresh_preview = service.preview_approval(fresh_approval.id)
            with pytest.raises(PaperLifecycleError, match="stale_preview"):
                service.submit_approval(fresh_approval.id, preview_digest="old-preview")

            with pytest.raises(PaperLifecycleError, match="entry_window_closed"):
                closed_service.submit_approval(
                    fresh_approval.id,
                    preview_digest=fresh_preview.preview_digest,
                )

            with pytest.raises(PaperLifecycleError, match="approval_not_found"):
                service.preview_approval("missing-approval")
    finally:
        engine.dispose()


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
