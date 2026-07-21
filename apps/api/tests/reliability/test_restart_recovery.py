from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.domain.time import FrozenClock
from market_trader.paper.models import (
    ApprovalCard,
    ApprovalCardState,
    PaperAction,
    PaperBrokerScenario,
)
from market_trader.paper.service import PaperLifecycleService
from market_trader.recovery.restart import run_restart_recovery_drill
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.orders import TradeLifecycleRepository
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_restart_recovery_drill_prioritizes_open_positions_orders_timeouts_and_approvals(
    tmp_path: Path,
) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            service = PaperLifecycleService(session, clock=FrozenClock(AS_OF))
            expiring_approval = service.approve_card(_card("expiring"))
            working_approval = service.approve_card(_card("working"))
            working_preview = service.preview_approval(working_approval.id)
            service.submit_approval(
                working_approval.id,
                preview_digest=working_preview.preview_digest,
                scenario=PaperBrokerScenario.ACCEPTED_UNFILLED,
            )
            timeout_approval = service.approve_card(_card("timeout"))
            timeout_preview = service.preview_approval(timeout_approval.id)
            service.submit_approval(
                timeout_approval.id,
                preview_digest=timeout_preview.preview_digest,
                scenario=PaperBrokerScenario.TIMEOUT,
            )
            filled_approval = service.approve_card(_card("position"))
            filled_preview = service.preview_approval(filled_approval.id)
            service.submit_approval(
                filled_approval.id,
                preview_digest=filled_preview.preview_digest,
                scenario=PaperBrokerScenario.FULL_FILL,
            )
            session.commit()

        with Session(engine) as session:
            report = run_restart_recovery_drill(
                session,
                correlation_id="corr-restart-drill",
                clock=FrozenClock(AS_OF),
            )
            events = AuditRepository(session).list_by_correlation_id("corr-restart-drill")
            repository = TradeLifecycleRepository(session)
            open_positions = repository.list_positions_by_status({"open"})
            working_orders = repository.list_orders_by_status({"working"})
            timed_out_orders = repository.list_orders_by_status({"timed_out"})

        assert [action.code for action in report.actions] == [
            "open_position_reconcile",
            "working_order_reconcile",
            "timed_out_broker_request",
            "expiring_approval_review",
        ]
        assert [action.subject_id for action in report.actions] == [
            open_positions[0].id,
            working_orders[0].id,
            timed_out_orders[0].id,
            expiring_approval.id,
        ]
        assert report.counts == {
            "open_positions": 1,
            "working_orders": 1,
            "timed_out_orders": 1,
            "expiring_approvals": 1,
        }
        assert [event.event_type for event in events] == ["recovery.restart_drill_completed"]
        assert events[0].payload["action_codes"] == [action.code for action in report.actions]
    finally:
        engine.dispose()


def _card(candidate_key: str) -> ApprovalCard:
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
