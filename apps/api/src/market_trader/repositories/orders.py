from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import (
    ApprovalORM,
    FillORM,
    OrderORM,
    PositionORM,
    ProposedTradeORM,
)
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


@dataclass(frozen=True)
class ProposedTradeCreate:
    candidate_id: str | None
    status: str
    order_intent_payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


@dataclass(frozen=True)
class ProposedTrade:
    id: str
    candidate_id: str | None
    status: str
    order_intent_payload: dict[str, Any]
    payload_schema_version: int
    broker_reference: str | None
    simulated_broker_reference: str | None
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


@dataclass(frozen=True)
class ApprovalCreate:
    proposed_trade_id: str
    status: str
    actor_type: str
    decision_payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


@dataclass(frozen=True)
class Approval:
    id: str
    proposed_trade_id: str
    status: str
    actor_type: str
    decision_payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


@dataclass(frozen=True)
class OrderRecordCreate:
    proposed_trade_id: str | None
    approval_id: str | None
    status: str
    order_intent_payload: dict[str, Any]
    payload_schema_version: int
    broker_reference: str | None
    simulated_broker_reference: str | None
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


@dataclass(frozen=True)
class OrderRecord:
    id: str
    proposed_trade_id: str | None
    approval_id: str | None
    status: str
    order_intent_payload: dict[str, Any]
    payload_schema_version: int
    broker_reference: str | None
    simulated_broker_reference: str | None
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


@dataclass(frozen=True)
class FillCreate:
    order_id: str
    status: str
    quantity: Decimal
    price: Decimal
    broker_reference: str | None
    simulated_broker_reference: str | None
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    occurred_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class Fill:
    id: str
    order_id: str
    status: str
    quantity: Decimal
    price: Decimal
    broker_reference: str | None
    simulated_broker_reference: str | None
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    occurred_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class PositionCreate:
    symbol_id: str
    instrument_id: str | None
    status: str
    quantity: Decimal
    average_price: Decimal | None
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True)
class Position:
    id: str
    symbol_id: str
    instrument_id: str | None
    status: str
    quantity: Decimal
    average_price: Decimal | None
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class TradeLifecycleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def create_proposed_trade(self, command: ProposedTradeCreate) -> ProposedTrade:
        record = ProposedTradeORM(
            id=new_domain_id("ptr"),
            candidate_id=command.candidate_id,
            status=command.status,
            order_intent_payload=dict(command.order_intent_payload),
            payload_schema_version=command.payload_schema_version,
            broker_reference=None,
            simulated_broker_reference=None,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
            updated_at=ensure_utc(command.updated_at),
            terminal_at=_optional_utc(command.terminal_at),
        )
        self._persist_with_audit(
            record,
            event_type="proposed_trade.created",
            subject_type="proposed_trade",
            correlation_id=command.correlation_id,
            occurred_at=command.created_at,
        )
        return _proposed_trade_to_domain(record)

    def create_approval(self, command: ApprovalCreate) -> Approval:
        record = ApprovalORM(
            id=new_domain_id("apr"),
            proposed_trade_id=command.proposed_trade_id,
            status=command.status,
            actor_type=command.actor_type,
            decision_payload=dict(command.decision_payload),
            payload_schema_version=command.payload_schema_version,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
            updated_at=ensure_utc(command.updated_at),
            terminal_at=_optional_utc(command.terminal_at),
        )
        self._persist_with_audit(
            record,
            event_type="approval.created",
            subject_type="approval",
            correlation_id=command.correlation_id,
            occurred_at=command.created_at,
        )
        return _approval_to_domain(record)

    def create_order_record(self, command: OrderRecordCreate) -> OrderRecord:
        record = OrderORM(
            id=new_domain_id("ord"),
            proposed_trade_id=command.proposed_trade_id,
            approval_id=command.approval_id,
            status=command.status,
            order_intent_payload=dict(command.order_intent_payload),
            payload_schema_version=command.payload_schema_version,
            broker_reference=command.broker_reference,
            simulated_broker_reference=command.simulated_broker_reference,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
            updated_at=ensure_utc(command.updated_at),
            terminal_at=_optional_utc(command.terminal_at),
        )
        self._persist_with_audit(
            record,
            event_type="order_record.created",
            subject_type="order",
            correlation_id=command.correlation_id,
            occurred_at=command.created_at,
        )
        return _order_to_domain(record)

    def create_fill_record(self, command: FillCreate) -> Fill:
        record = FillORM(
            id=new_domain_id("fil"),
            order_id=command.order_id,
            status=command.status,
            quantity=command.quantity,
            price=command.price,
            broker_reference=command.broker_reference,
            simulated_broker_reference=command.simulated_broker_reference,
            payload=dict(command.payload),
            payload_schema_version=command.payload_schema_version,
            correlation_id=command.correlation_id,
            occurred_at=ensure_utc(command.occurred_at),
            created_at=ensure_utc(command.created_at),
        )
        self._persist_with_audit(
            record,
            event_type="fill_record.created",
            subject_type="fill",
            correlation_id=command.correlation_id,
            occurred_at=command.occurred_at,
        )
        return _fill_to_domain(record)

    def create_position_record(self, command: PositionCreate) -> Position:
        record = PositionORM(
            id=new_domain_id("pos"),
            symbol_id=command.symbol_id,
            instrument_id=command.instrument_id,
            status=command.status,
            quantity=command.quantity,
            average_price=command.average_price,
            payload=dict(command.payload),
            payload_schema_version=command.payload_schema_version,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
            updated_at=ensure_utc(command.updated_at),
            closed_at=_optional_utc(command.closed_at),
        )
        self._persist_with_audit(
            record,
            event_type="position_record.created",
            subject_type="position",
            correlation_id=command.correlation_id,
            occurred_at=command.created_at,
        )
        return _position_to_domain(record)

    def get_proposed_trade(self, record_id: str) -> ProposedTrade | None:
        record = self._session.get(ProposedTradeORM, record_id)
        return _proposed_trade_to_domain(record) if record is not None else None

    def get_approval(self, record_id: str) -> Approval | None:
        record = self._session.get(ApprovalORM, record_id)
        return _approval_to_domain(record) if record is not None else None

    def get_order(self, record_id: str) -> OrderRecord | None:
        record = self._session.get(OrderORM, record_id)
        return _order_to_domain(record) if record is not None else None

    def get_fill(self, record_id: str) -> Fill | None:
        record = self._session.get(FillORM, record_id)
        return _fill_to_domain(record) if record is not None else None

    def get_position(self, record_id: str) -> Position | None:
        record = self._session.get(PositionORM, record_id)
        return _position_to_domain(record) if record is not None else None

    def update_proposed_trade_status(
        self,
        record_id: str,
        *,
        status: str,
        updated_at: datetime,
        terminal_at: datetime | None,
        correlation_id: str,
    ) -> ProposedTrade | None:
        record = self._session.get(ProposedTradeORM, record_id)
        if record is None:
            return None
        self._update_terminal_status(
            record,
            status=status,
            updated_at=updated_at,
            terminal_at=terminal_at,
            correlation_id=correlation_id,
            event_type="proposed_trade.status_updated",
            subject_type="proposed_trade",
        )
        return _proposed_trade_to_domain(record)

    def update_approval_status(
        self,
        record_id: str,
        *,
        status: str,
        updated_at: datetime,
        terminal_at: datetime | None,
        correlation_id: str,
    ) -> Approval | None:
        record = self._session.get(ApprovalORM, record_id)
        if record is None:
            return None
        self._update_terminal_status(
            record,
            status=status,
            updated_at=updated_at,
            terminal_at=terminal_at,
            correlation_id=correlation_id,
            event_type="approval.status_updated",
            subject_type="approval",
        )
        return _approval_to_domain(record)

    def update_order_status(
        self,
        record_id: str,
        *,
        status: str,
        updated_at: datetime,
        terminal_at: datetime | None,
        correlation_id: str,
        simulated_broker_reference: str | None = None,
    ) -> OrderRecord | None:
        record = self._session.get(OrderORM, record_id)
        if record is None:
            return None
        if simulated_broker_reference is not None:
            record.simulated_broker_reference = simulated_broker_reference
        self._update_terminal_status(
            record,
            status=status,
            updated_at=updated_at,
            terminal_at=terminal_at,
            correlation_id=correlation_id,
            event_type="order.status_updated",
            subject_type="order",
        )
        return _order_to_domain(record)

    def update_position_status(
        self,
        record_id: str,
        *,
        status: str,
        quantity: Decimal,
        average_price: Decimal | None,
        updated_at: datetime,
        closed_at: datetime | None,
        correlation_id: str,
    ) -> Position | None:
        record = self._session.get(PositionORM, record_id)
        if record is None:
            return None
        record.status = status
        record.quantity = quantity
        record.average_price = average_price
        record.updated_at = ensure_utc(updated_at)
        record.closed_at = _optional_utc(closed_at)
        self._session.flush()
        self._append_audit(
            event_type="position.status_updated",
            subject_type="position",
            subject_id=record.id,
            status=status,
            correlation_id=correlation_id,
            occurred_at=updated_at,
        )
        return _position_to_domain(record)

    def list_orders_by_status(self, statuses: set[str]) -> tuple[OrderRecord, ...]:
        if not statuses:
            return ()
        records = self._session.scalars(
            select(OrderORM)
            .where(OrderORM.status.in_(statuses))
            .order_by(OrderORM.created_at, OrderORM.id)
        ).all()
        return tuple(_order_to_domain(record) for record in records)

    def list_fills_for_order(self, order_id: str) -> tuple[Fill, ...]:
        records = self._session.scalars(
            select(FillORM)
            .where(FillORM.order_id == order_id)
            .order_by(FillORM.occurred_at, FillORM.id)
        ).all()
        return tuple(_fill_to_domain(record) for record in records)

    def list_positions_by_status(self, statuses: set[str]) -> tuple[Position, ...]:
        if not statuses:
            return ()
        records = self._session.scalars(
            select(PositionORM)
            .where(PositionORM.status.in_(statuses))
            .order_by(PositionORM.updated_at, PositionORM.id)
        ).all()
        return tuple(_position_to_domain(record) for record in records)

    def _update_terminal_status(
        self,
        record: ProposedTradeORM | ApprovalORM | OrderORM,
        *,
        status: str,
        updated_at: datetime,
        terminal_at: datetime | None,
        correlation_id: str,
        event_type: str,
        subject_type: str,
    ) -> None:
        record.status = status
        record.updated_at = ensure_utc(updated_at)
        record.terminal_at = _optional_utc(terminal_at)
        self._session.flush()
        self._append_audit(
            event_type=event_type,
            subject_type=subject_type,
            subject_id=record.id,
            status=status,
            correlation_id=correlation_id,
            occurred_at=updated_at,
        )

    def _persist_with_audit(
        self,
        record: ProposedTradeORM | ApprovalORM | OrderORM | FillORM | PositionORM,
        *,
        event_type: str,
        subject_type: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> None:
        self._session.add(record)
        self._session.flush()
        self._append_audit(
            event_type=event_type,
            subject_type=subject_type,
            subject_id=record.id,
            status=record.status,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
        )

    def _append_audit(
        self,
        *,
        event_type: str,
        subject_type: str,
        subject_id: str,
        status: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> None:
        self._audit.append(
            AuditEventCreate(
                correlation_id=correlation_id,
                event_type=event_type,
                actor_type="system",
                occurred_at=occurred_at,
                subject_type=subject_type,
                subject_id=subject_id,
                payload={"schema_version": 1, "status": status},
                schema_version=1,
            )
        )


def _optional_utc(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


def _proposed_trade_to_domain(record: ProposedTradeORM) -> ProposedTrade:
    return ProposedTrade(
        id=record.id,
        candidate_id=record.candidate_id,
        status=record.status,
        order_intent_payload=dict(record.order_intent_payload),
        payload_schema_version=record.payload_schema_version,
        broker_reference=record.broker_reference,
        simulated_broker_reference=record.simulated_broker_reference,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
        updated_at=stored_utc(record.updated_at),
        terminal_at=stored_utc(record.terminal_at) if record.terminal_at is not None else None,
    )


def _approval_to_domain(record: ApprovalORM) -> Approval:
    return Approval(
        id=record.id,
        proposed_trade_id=record.proposed_trade_id,
        status=record.status,
        actor_type=record.actor_type,
        decision_payload=dict(record.decision_payload),
        payload_schema_version=record.payload_schema_version,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
        updated_at=stored_utc(record.updated_at),
        terminal_at=stored_utc(record.terminal_at) if record.terminal_at is not None else None,
    )


def _order_to_domain(record: OrderORM) -> OrderRecord:
    return OrderRecord(
        id=record.id,
        proposed_trade_id=record.proposed_trade_id,
        approval_id=record.approval_id,
        status=record.status,
        order_intent_payload=dict(record.order_intent_payload),
        payload_schema_version=record.payload_schema_version,
        broker_reference=record.broker_reference,
        simulated_broker_reference=record.simulated_broker_reference,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
        updated_at=stored_utc(record.updated_at),
        terminal_at=stored_utc(record.terminal_at) if record.terminal_at is not None else None,
    )


def _fill_to_domain(record: FillORM) -> Fill:
    return Fill(
        id=record.id,
        order_id=record.order_id,
        status=record.status,
        quantity=record.quantity,
        price=record.price,
        broker_reference=record.broker_reference,
        simulated_broker_reference=record.simulated_broker_reference,
        payload=dict(record.payload),
        payload_schema_version=record.payload_schema_version,
        correlation_id=record.correlation_id,
        occurred_at=stored_utc(record.occurred_at),
        created_at=stored_utc(record.created_at),
    )


def _position_to_domain(record: PositionORM) -> Position:
    return Position(
        id=record.id,
        symbol_id=record.symbol_id,
        instrument_id=record.instrument_id,
        status=record.status,
        quantity=record.quantity,
        average_price=record.average_price,
        payload=dict(record.payload),
        payload_schema_version=record.payload_schema_version,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
        updated_at=stored_utc(record.updated_at),
        closed_at=stored_utc(record.closed_at) if record.closed_at is not None else None,
    )
