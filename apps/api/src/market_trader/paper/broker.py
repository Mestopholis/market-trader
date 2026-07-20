from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from market_trader.domain.time import ensure_utc
from market_trader.paper.models import (
    LifecycleEvent,
    PaperBrokerOrder,
    PaperBrokerScenario,
    PaperOrderIntent,
    PaperOrderStatus,
    PaperPosition,
    PaperPositionStatus,
    PaperPreview,
)


@dataclass(frozen=True)
class PaperBrokerResult:
    order: PaperBrokerOrder
    events: tuple[LifecycleEvent, ...]
    position: PaperPosition | None = None


class DeterministicPaperBroker:
    def execute(
        self,
        *,
        intent: PaperOrderIntent,
        preview: PaperPreview,
        scenario: PaperBrokerScenario,
        as_of: datetime,
    ) -> PaperBrokerResult:
        occurred_at = ensure_utc(as_of)
        order_id = f"paper-order-{intent.intent_key}-{scenario.value}"
        simulated_reference = f"sim-{order_id}"
        status, filled_quantity, terminal = _scenario_order_state(scenario, intent.quantity)
        remaining_quantity = intent.quantity - filled_quantity
        average_fill_price = _fill_price(intent, preview) if filled_quantity > 0 else None
        terminal_at = occurred_at if terminal else None
        source_keys = (*intent.source_keys, f"preview:{preview.preview_key}")

        order = PaperBrokerOrder(
            order_id=order_id,
            intent_key=intent.intent_key,
            status=status,
            scenario=scenario,
            requested_quantity=intent.quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            limit_price=intent.limit_price,
            average_fill_price=average_fill_price,
            simulated_broker_reference=simulated_reference,
            correlation_id=intent.correlation_id,
            source_keys=source_keys,
            created_at=occurred_at,
            updated_at=occurred_at,
            terminal_at=terminal_at,
        )
        events = _events_for_order(
            order=order,
            intent=intent,
            occurred_at=occurred_at,
            reason_codes=_reason_codes(scenario),
        )
        position = _position_for_order(order, intent=intent, occurred_at=occurred_at)
        return PaperBrokerResult(order=order, events=events, position=position)


def _scenario_order_state(
    scenario: PaperBrokerScenario, quantity: int
) -> tuple[PaperOrderStatus, int, bool]:
    if scenario is PaperBrokerScenario.ACCEPTED_UNFILLED:
        return PaperOrderStatus.WORKING, 0, False
    if scenario is PaperBrokerScenario.FULL_FILL:
        return PaperOrderStatus.FILLED, quantity, True
    if scenario is PaperBrokerScenario.PARTIAL_FILL:
        return PaperOrderStatus.PARTIALLY_FILLED, max(1, quantity // 2), False
    if scenario is PaperBrokerScenario.REJECT:
        return PaperOrderStatus.REJECTED, 0, True
    if scenario is PaperBrokerScenario.CANCEL:
        return PaperOrderStatus.CANCELED, 0, True
    if scenario is PaperBrokerScenario.CANCEL_REPLACE:
        return PaperOrderStatus.REPLACED, 0, True
    if scenario is PaperBrokerScenario.TIMEOUT:
        return PaperOrderStatus.TIMED_OUT, 0, True
    return PaperOrderStatus.FILLED, quantity, True


def _fill_price(intent: PaperOrderIntent, preview: PaperPreview) -> Decimal:
    return preview.ask if intent.side == "buy" else preview.bid


def _events_for_order(
    *,
    order: PaperBrokerOrder,
    intent: PaperOrderIntent,
    occurred_at: datetime,
    reason_codes: tuple[str, ...],
) -> tuple[LifecycleEvent, ...]:
    events = [
        _event(
            event_type="paper_order.accepted",
            order=order,
            intent=intent,
            occurred_at=occurred_at,
            reason_codes=reason_codes,
        )
    ]
    if order.filled_quantity > 0:
        events.append(
            _event(
                event_type="paper_order.filled",
                order=order,
                intent=intent,
                occurred_at=occurred_at,
                reason_codes=reason_codes,
            )
        )
    if order.scenario is PaperBrokerScenario.ASSIGNMENT:
        events.append(
            _event(
                event_type="paper_position.assigned",
                order=order,
                intent=intent,
                occurred_at=occurred_at,
                reason_codes=reason_codes,
            )
        )
    return tuple(events)


def _event(
    *,
    event_type: str,
    order: PaperBrokerOrder,
    intent: PaperOrderIntent,
    occurred_at: datetime,
    reason_codes: tuple[str, ...],
) -> LifecycleEvent:
    return LifecycleEvent(
        event_key=f"{event_type}:{order.order_id}",
        event_type=event_type,
        subject_type="paper_order",
        subject_id=order.order_id,
        occurred_at=occurred_at,
        correlation_id=intent.correlation_id,
        source_keys=(f"paper_order:{order.order_id}", *order.source_keys),
        payload={
            "schema_version": 1,
            "source_order_id": order.order_id,
            "simulated_broker_reference": order.simulated_broker_reference,
            "status": order.status.value,
            "reason_codes": list(reason_codes),
        },
    )


def _reason_codes(scenario: PaperBrokerScenario) -> tuple[str, ...]:
    if scenario is PaperBrokerScenario.REJECT:
        return ("paper_reject",)
    if scenario is PaperBrokerScenario.TIMEOUT:
        return ("paper_timeout",)
    if scenario is PaperBrokerScenario.CANCEL:
        return ("paper_cancel",)
    if scenario is PaperBrokerScenario.CANCEL_REPLACE:
        return ("paper_cancel_replace",)
    if scenario is PaperBrokerScenario.ASSIGNMENT:
        return ("paper_assignment",)
    return ()


def _position_for_order(
    order: PaperBrokerOrder, *, intent: PaperOrderIntent, occurred_at: datetime
) -> PaperPosition | None:
    if order.average_fill_price is None:
        return None
    status = (
        PaperPositionStatus.ASSIGNED
        if order.scenario is PaperBrokerScenario.ASSIGNMENT
        else PaperPositionStatus.OPEN
    )
    return PaperPosition(
        position_key=f"paper-position-{intent.intent_key}",
        symbol=intent.symbol,
        status=status,
        quantity=order.filled_quantity,
        average_price=order.average_fill_price,
        realized_pl=Decimal("0"),
        unrealized_pl=Decimal("0"),
        source_order_ids=(order.order_id,),
        source_fill_ids=(f"paper-fill-{order.order_id}",),
        risk_decision_key=intent.risk_decision_key,
        opened_at=occurred_at,
        updated_at=occurred_at,
        closed_at=None,
        exit_rules={"schema_version": 1},
    )
