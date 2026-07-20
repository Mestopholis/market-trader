from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import ApprovalORM, OrderORM, RiskLockORM, SymbolORM
from market_trader.domain.time import Clock, SystemClock, ensure_utc
from market_trader.paper.broker import DeterministicPaperBroker
from market_trader.paper.eligibility import REQUIRED_CLEAR_LOCK_TYPES, assemble_approval_cards
from market_trader.paper.models import (
    ApprovalCard,
    ApprovalCardState,
    PaperBrokerOrder,
    PaperBrokerScenario,
    PaperOrderIntent,
    PaperOrderStatus,
    PaperOrderType,
    PaperPosition,
    PaperPreview,
)
from market_trader.repositories.orders import (
    Approval,
    ApprovalCreate,
    FillCreate,
    OrderRecord,
    OrderRecordCreate,
    Position,
    PositionCreate,
    ProposedTradeCreate,
    TradeLifecycleRepository,
)

PREVIEW_TTL = timedelta(minutes=1)
OPEN_ORDER_STATUSES = {"accepted", "working", "partially_filled", "timed_out"}
OPEN_POSITION_STATUSES = {"open", "partially_closed"}
OPEN_APPROVAL_STATUSES = {"approved"}
WORKING_ORDER_STATUSES = {"accepted", "working", "partially_filled"}
TIMED_OUT_ORDER_STATUSES = {"timed_out"}


class PaperLifecycleError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SubmittedPaperOrder:
    order: PaperBrokerOrder
    persisted_order_id: str
    position: PaperPosition | None


@dataclass(frozen=True)
class PaperRecoveryState:
    open_approvals: tuple[Approval, ...]
    working_orders: tuple[OrderRecord, ...]
    timed_out_orders: tuple[OrderRecord, ...]
    open_orders: tuple[OrderRecord, ...]
    open_positions: tuple[Position, ...]


class PaperLifecycleService:
    def __init__(
        self,
        session: Session,
        *,
        clock: Clock | None = None,
        entry_window_open: bool = True,
        broker: DeterministicPaperBroker | None = None,
    ) -> None:
        self._session = session
        self._clock = clock or SystemClock()
        self._entry_window_open = entry_window_open
        self._broker = broker or DeterministicPaperBroker()
        self._repository = TradeLifecycleRepository(session)

    def approval_cards(self) -> tuple[ApprovalCard, ...]:
        return assemble_approval_cards(self._session, as_of=self._now())

    def approve_card(self, card: ApprovalCard) -> Approval:
        self._ensure_card_actionable(card)
        return self._create_approval(card, status="approved", intent=_intent_from_card(card))

    def modify_card(
        self, card: ApprovalCard, *, quantity: int, limit_price: Decimal
    ) -> Approval:
        self._ensure_card_actionable(card)
        intent = _intent_from_card(card, quantity=quantity, limit_price=limit_price)
        return self._create_approval(card, status="approved", intent=intent)

    def reject_card(self, card: ApprovalCard) -> Approval:
        self._ensure_card_actionable(card, allow_expired=True)
        return self._create_approval(card, status="rejected", intent=None, terminal=True)

    def preview_approval(self, approval_id: str) -> PaperPreview:
        approval_record = self._approval_record(approval_id)
        payload = _payload(approval_record.decision_payload)
        intent = _intent_from_payload(payload)
        now = self._now()
        preview = PaperPreview(
            preview_key=f"preview-{approval_record.id}",
            approval_id=approval_record.id,
            intent_key=intent.intent_key,
            quote_observed_at=now,
            quote_expires_at=now + PREVIEW_TTL,
            bid=max(intent.limit_price - Decimal("0.15"), Decimal("0.01")),
            ask=intent.limit_price + Decimal("0.05"),
            limit_price=intent.limit_price,
            estimated_maximum_loss=intent.limit_price * Decimal(intent.quantity) * Decimal("100"),
            reserved_risk=intent.limit_price * Decimal(intent.quantity) * Decimal("100"),
            warnings=(),
            preview_digest=f"preview-{approval_record.id}-{intent.intent_key}",
            source_keys=(*intent.source_keys, f"approval:{approval_record.id}"),
            as_of=now,
        )
        payload["preview"] = _preview_payload(preview)
        approval_record.decision_payload = payload
        self._session.flush()
        return preview

    def submit_approval(
        self,
        approval_id: str,
        *,
        preview_digest: str,
        scenario: PaperBrokerScenario = PaperBrokerScenario.FULL_FILL,
    ) -> SubmittedPaperOrder:
        if not self._entry_window_open:
            raise PaperLifecycleError("entry_window_closed")
        approval_record = self._approval_record(approval_id)
        payload = _payload(approval_record.decision_payload)
        intent = _intent_from_payload(payload)
        preview = _preview_from_payload(payload)
        if preview.preview_digest != preview_digest:
            raise PaperLifecycleError("stale_preview")
        if preview.quote_expires_at < self._now():
            raise PaperLifecycleError("stale_preview")
        self._ensure_risk_digest_current(payload)

        now = self._now()
        result = self._broker.execute(
            intent=intent,
            preview=preview,
            scenario=scenario,
            as_of=now,
        )
        order_record = self._repository.create_order_record(
            OrderRecordCreate(
                proposed_trade_id=intent.proposed_trade_id,
                approval_id=approval_record.id,
                status="accepted",
                order_intent_payload={
                    "schema_version": 1,
                    "intent": _intent_payload(intent),
                    "paper_order_id": result.order.order_id,
                },
                payload_schema_version=1,
                broker_reference=None,
                simulated_broker_reference=result.order.simulated_broker_reference,
                correlation_id=intent.correlation_id,
                created_at=now,
                updated_at=now,
                terminal_at=None,
            )
        )
        self._repository.update_order_status(
            order_record.id,
            status=result.order.status.value,
            updated_at=now,
            terminal_at=result.order.terminal_at,
            correlation_id=intent.correlation_id,
            simulated_broker_reference=result.order.simulated_broker_reference,
        )
        if result.order.filled_quantity > 0 and result.order.average_fill_price is not None:
            self._repository.create_fill_record(
                FillCreate(
                    order_id=order_record.id,
                    status="recorded",
                    quantity=Decimal(result.order.filled_quantity),
                    price=result.order.average_fill_price,
                    broker_reference=None,
                    simulated_broker_reference=f"paper-fill-{result.order.order_id}",
                    payload={"schema_version": 1, "paper_order_id": result.order.order_id},
                    payload_schema_version=1,
                    correlation_id=intent.correlation_id,
                    occurred_at=now,
                    created_at=now,
                )
            )
        if result.position is not None:
            self._persist_position(result.position, correlation_id=intent.correlation_id)
        return SubmittedPaperOrder(
            order=result.order,
            persisted_order_id=order_record.id,
            position=result.position,
        )

    def cancel_order(self, order_id: str) -> OrderRecord:
        now = self._now()
        updated = self._repository.update_order_status(
            self._persisted_order_id(order_id),
            status=PaperOrderStatus.CANCELED.value,
            updated_at=now,
            terminal_at=now,
            correlation_id="corr-paper-cancel",
        )
        if updated is None:
            raise PaperLifecycleError("order_not_found")
        return updated

    def replace_order(self, order_id: str, *, limit_price: Decimal) -> OrderRecord:
        if limit_price <= 0:
            raise PaperLifecycleError("invalid_limit_price")
        now = self._now()
        updated = self._repository.update_order_status(
            self._persisted_order_id(order_id),
            status=PaperOrderStatus.REPLACED.value,
            updated_at=now,
            terminal_at=now,
            correlation_id="corr-paper-replace",
        )
        if updated is None:
            raise PaperLifecycleError("order_not_found")
        return updated

    def recover(self) -> PaperRecoveryState:
        working_orders = self._repository.list_orders_by_status(WORKING_ORDER_STATUSES)
        timed_out_orders = self._repository.list_orders_by_status(TIMED_OUT_ORDER_STATUSES)
        return PaperRecoveryState(
            open_approvals=self._recoverable_approvals(),
            working_orders=working_orders,
            timed_out_orders=timed_out_orders,
            open_orders=(*working_orders, *timed_out_orders),
            open_positions=self._repository.list_positions_by_status(OPEN_POSITION_STATUSES),
        )

    def _recoverable_approvals(self) -> tuple[Approval, ...]:
        open_approvals = self._repository.list_approvals_by_status(OPEN_APPROVAL_STATUSES)
        orders = self._repository.list_orders_by_status(
            OPEN_ORDER_STATUSES | {"filled", "replaced", "canceled"}
        )
        submitted_approval_ids = {
            order.approval_id for order in orders if order.approval_id is not None
        }
        return tuple(
            approval for approval in open_approvals if approval.id not in submitted_approval_ids
        )

    def _create_approval(
        self,
        card: ApprovalCard,
        *,
        status: str,
        intent: PaperOrderIntent | None,
        terminal: bool = False,
    ) -> Approval:
        now = self._now()
        proposed = self._repository.create_proposed_trade(
            ProposedTradeCreate(
                candidate_id=None,
                status=status,
                order_intent_payload={
                    "schema_version": 1,
                    "card_key": card.card_key,
                    "intent": _intent_payload(intent) if intent is not None else None,
                },
                payload_schema_version=1,
                correlation_id=f"corr-paper-{card.candidate_key}",
                created_at=now,
                updated_at=now,
                terminal_at=now if terminal else None,
            )
        )
        if intent is not None:
            intent = intent.model_copy(update={"proposed_trade_id": proposed.id})
        return self._repository.create_approval(
            ApprovalCreate(
                proposed_trade_id=proposed.id,
                status=status,
                actor_type="operator",
                decision_payload={
                    "schema_version": 1,
                    "card": _card_payload(card),
                    "intent": _intent_payload(intent) if intent is not None else None,
                },
                payload_schema_version=1,
                correlation_id=f"corr-paper-{card.candidate_key}",
                created_at=now,
                updated_at=now,
                terminal_at=now if terminal else None,
            )
        )

    def _ensure_card_actionable(self, card: ApprovalCard, *, allow_expired: bool = False) -> None:
        if self._has_active_required_lock():
            raise PaperLifecycleError("active_risk_lock")
        if card.state is not ApprovalCardState.READY:
            raise PaperLifecycleError("approval_unavailable")
        if not allow_expired and card.expires_at < self._now():
            raise PaperLifecycleError("approval_expired")

    def _has_active_required_lock(self) -> bool:
        return (
            self._session.scalar(
                select(RiskLockORM.id)
                .where(RiskLockORM.status == "active")
                .where(RiskLockORM.lock_type.in_(REQUIRED_CLEAR_LOCK_TYPES))
                .limit(1)
            )
            is not None
        )

    def _approval_record(self, approval_id: str) -> ApprovalORM:
        approval = self._session.get(ApprovalORM, approval_id)
        if approval is None:
            raise PaperLifecycleError("approval_not_found")
        return approval

    def _ensure_risk_digest_current(self, payload: dict[str, Any]) -> None:
        card = _card_from_payload(payload)
        expected = f"risk-result-{card.candidate_key}"
        if card.risk_result_digest != expected:
            raise PaperLifecycleError("risk_digest_changed")

    def _persist_position(self, position: PaperPosition, *, correlation_id: str) -> None:
        now = self._now()
        symbol = self._session.scalar(
            select(SymbolORM).where(SymbolORM.display_symbol == position.symbol).limit(1)
        )
        if symbol is None:
            symbol = SymbolORM(
                id=f"paper-symbol-{position.symbol}",
                display_symbol=position.symbol,
                instrument_type="equity",
                exchange=None,
                is_active=True,
                first_observed_at=now,
                last_observed_at=now,
                metadata_payload={"schema_version": 1},
                metadata_schema_version=1,
                correlation_id=correlation_id,
            )
            self._session.add(symbol)
            self._session.flush()
        self._repository.create_position_record(
            PositionCreate(
                symbol_id=symbol.id,
                instrument_id=None,
                status=position.status.value,
                quantity=Decimal(position.quantity),
                average_price=position.average_price,
                payload={"schema_version": 1, "position_key": position.position_key},
                payload_schema_version=1,
                correlation_id=correlation_id,
                created_at=now,
                updated_at=now,
                closed_at=position.closed_at,
            )
        )

    def _persisted_order_id(self, order_id: str) -> str:
        if self._session.get(OrderORM, order_id) is not None:
            return order_id
        stored_id = self._session.scalar(
            select(OrderORM.id)
            .where(OrderORM.order_intent_payload["paper_order_id"].as_string() == order_id)
            .limit(1)
        )
        if stored_id is None:
            raise PaperLifecycleError("order_not_found")
        return stored_id

    def _now(self) -> datetime:
        return ensure_utc(self._clock.now())


def _intent_from_card(
    card: ApprovalCard,
    *,
    quantity: int | None = None,
    limit_price: Decimal | None = None,
) -> PaperOrderIntent:
    return PaperOrderIntent(
        intent_key=f"intent-{card.card_key}",
        approval_id=f"pending-{card.card_key}",
        proposed_trade_id=f"pending-{card.card_key}",
        risk_decision_key=card.risk_decision_key,
        symbol=card.symbol,
        side="buy" if card.direction == "long" else "sell",
        order_type=PaperOrderType.LIMIT,
        quantity=quantity or card.quantity,
        limit_price=limit_price or card.limit_price,
        time_in_force="day",
        source_keys=(*card.source_keys, f"approval_card:{card.card_key}"),
        correlation_id=f"corr-paper-{card.candidate_key}",
        created_at=card.as_of,
        payload={"schema_version": 1},
    )


def _payload(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    raise PaperLifecycleError("invalid_payload")


def _card_payload(card: ApprovalCard) -> dict[str, Any]:
    return card.model_dump(mode="json")


def _card_from_payload(payload: dict[str, Any]) -> ApprovalCard:
    card_payload = payload.get("card")
    if not isinstance(card_payload, dict):
        raise PaperLifecycleError("missing_source_records")
    return ApprovalCard.model_validate(card_payload)


def _intent_payload(intent: PaperOrderIntent | None) -> dict[str, Any] | None:
    return intent.model_dump(mode="json") if intent is not None else None


def _intent_from_payload(payload: dict[str, Any]) -> PaperOrderIntent:
    intent_payload = payload.get("intent")
    if not isinstance(intent_payload, dict):
        raise PaperLifecycleError("missing_source_records")
    return PaperOrderIntent.model_validate(intent_payload)


def _preview_payload(preview: PaperPreview) -> dict[str, Any]:
    return preview.model_dump(mode="json")


def _preview_from_payload(payload: dict[str, Any]) -> PaperPreview:
    preview_payload = payload.get("preview")
    if not isinstance(preview_payload, dict):
        raise PaperLifecycleError("stale_preview")
    return PaperPreview.model_validate(preview_payload)
