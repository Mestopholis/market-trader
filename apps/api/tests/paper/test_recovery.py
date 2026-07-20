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
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def test_recovery_prioritizes_open_approvals_orders_timeouts_and_positions(
    tmp_path: Path,
) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            service = PaperLifecycleService(session, clock=FrozenClock(AS_OF))
            open_approval = service.approve_card(_card(candidate_key="candidate-open"))
            working_approval = service.approve_card(_card(candidate_key="candidate-working"))
            working_preview = service.preview_approval(working_approval.id)
            service.submit_approval(
                working_approval.id,
                preview_digest=working_preview.preview_digest,
                scenario=PaperBrokerScenario.ACCEPTED_UNFILLED,
            )
            timeout_approval = service.approve_card(_card(candidate_key="candidate-timeout"))
            timeout_preview = service.preview_approval(timeout_approval.id)
            service.submit_approval(
                timeout_approval.id,
                preview_digest=timeout_preview.preview_digest,
                scenario=PaperBrokerScenario.TIMEOUT,
            )
            filled_approval = service.approve_card(_card(candidate_key="candidate-position"))
            filled_preview = service.preview_approval(filled_approval.id)
            service.submit_approval(
                filled_approval.id,
                preview_digest=filled_preview.preview_digest,
                scenario=PaperBrokerScenario.FULL_FILL,
            )
            session.commit()

        with Session(engine) as session:
            recovery = PaperLifecycleService(session, clock=FrozenClock(AS_OF)).recover()

        assert [approval.id for approval in recovery.open_approvals] == [open_approval.id]
        assert [order.status for order in recovery.working_orders] == ["working"]
        assert [order.status for order in recovery.timed_out_orders] == ["timed_out"]
        assert [order.status for order in recovery.open_orders] == ["working", "timed_out"]
        assert [position.status for position in recovery.open_positions] == ["open"]
    finally:
        engine.dispose()


def _card(*, candidate_key: str) -> ApprovalCard:
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
