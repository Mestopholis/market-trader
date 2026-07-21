from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy.orm import Session

from market_trader.domain.time import Clock, SystemClock, ensure_utc
from market_trader.paper.service import PaperLifecycleService
from market_trader.repositories.audit import AuditEventCreate, AuditRepository
from market_trader.repositories.orders import Approval, OrderRecord, Position

EXPIRING_APPROVAL_WINDOW = timedelta(minutes=10)


class RecoveryAction(BaseModel):
    priority: int
    code: str
    subject_type: str
    subject_id: str


class RestartRecoveryDrillReport(BaseModel):
    correlation_id: str
    generated_at: datetime
    counts: dict[str, int]
    actions: tuple[RecoveryAction, ...]
    recovery_event_id: str


def run_restart_recovery_drill(
    session: Session,
    *,
    correlation_id: str,
    clock: Clock | None = None,
    approval_expiry_window: timedelta = EXPIRING_APPROVAL_WINDOW,
) -> RestartRecoveryDrillReport:
    active_clock = clock or SystemClock()
    now = ensure_utc(active_clock.now())
    recovery = PaperLifecycleService(session, clock=active_clock).recover()
    expiring_approvals = tuple(
        approval
        for approval in recovery.open_approvals
        if _approval_expires_at(approval) <= now + approval_expiry_window
    )
    actions = (
        *_position_actions(recovery.open_positions),
        *_working_order_actions(recovery.working_orders),
        *_timed_out_order_actions(recovery.timed_out_orders),
        *_expiring_approval_actions(expiring_approvals),
    )
    counts = {
        "open_positions": len(recovery.open_positions),
        "working_orders": len(recovery.working_orders),
        "timed_out_orders": len(recovery.timed_out_orders),
        "expiring_approvals": len(expiring_approvals),
    }
    event = AuditRepository(session).append(
        AuditEventCreate(
            correlation_id=correlation_id,
            event_type="recovery.restart_drill_completed",
            actor_type="system",
            occurred_at=now,
            subject_type="restart_recovery",
            subject_id=correlation_id,
            payload={
                "schema_version": 1,
                "counts": counts,
                "action_codes": [action.code for action in actions],
                "action_subjects": [
                    {"type": action.subject_type, "id": action.subject_id}
                    for action in actions
                ],
            },
            schema_version=1,
        )
    )
    session.commit()
    return RestartRecoveryDrillReport(
        correlation_id=correlation_id,
        generated_at=now,
        counts=counts,
        actions=actions,
        recovery_event_id=event.id,
    )


def _position_actions(positions: tuple[Position, ...]) -> tuple[RecoveryAction, ...]:
    return tuple(
        RecoveryAction(
            priority=10,
            code="open_position_reconcile",
            subject_type="position",
            subject_id=position.id,
        )
        for position in positions
    )


def _working_order_actions(orders: tuple[OrderRecord, ...]) -> tuple[RecoveryAction, ...]:
    return tuple(
        RecoveryAction(
            priority=20,
            code="working_order_reconcile",
            subject_type="order",
            subject_id=order.id,
        )
        for order in orders
    )


def _timed_out_order_actions(orders: tuple[OrderRecord, ...]) -> tuple[RecoveryAction, ...]:
    return tuple(
        RecoveryAction(
            priority=30,
            code="timed_out_broker_request",
            subject_type="order",
            subject_id=order.id,
        )
        for order in orders
    )


def _expiring_approval_actions(approvals: tuple[Approval, ...]) -> tuple[RecoveryAction, ...]:
    return tuple(
        RecoveryAction(
            priority=40,
            code="expiring_approval_review",
            subject_type="approval",
            subject_id=approval.id,
        )
        for approval in approvals
    )


def _approval_expires_at(approval: Approval) -> datetime:
    card = approval.decision_payload.get("card")
    if not isinstance(card, dict):
        return approval.updated_at
    expires_at = card.get("expires_at")
    if not isinstance(expires_at, str):
        return approval.updated_at
    return ensure_utc(datetime.fromisoformat(expires_at))
