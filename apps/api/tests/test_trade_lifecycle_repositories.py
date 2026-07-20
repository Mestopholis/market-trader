from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.orders import (
    ApprovalCreate,
    FillCreate,
    OrderRecordCreate,
    PositionCreate,
    ProposedTradeCreate,
    TradeLifecycleRepository,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from tests.db_helpers import migrated_engine


def test_stores_trade_lifecycle_without_broker_operations(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    created_at = utc_now()
    try:
        with Session(engine) as session:
            symbol = SymbolRepository(session).create_symbol(
                SymbolCreate(
                    display_symbol="IWM",
                    instrument_type="equity",
                    exchange=None,
                    is_active=True,
                    first_observed_at=created_at,
                    last_observed_at=created_at,
                    metadata_payload={"schema_version": 1},
                    metadata_schema_version=1,
                    correlation_id="corr_setup",
                )
            )
            repository = TradeLifecycleRepository(session)
            proposed = repository.create_proposed_trade(
                ProposedTradeCreate(
                    candidate_id=None,
                    status="stored",
                    order_intent_payload={"schema_version": 1, "side": "buy"},
                    payload_schema_version=1,
                    correlation_id="corr_trade",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=None,
                )
            )
            approval = repository.create_approval(
                ApprovalCreate(
                    proposed_trade_id=proposed.id,
                    status="recorded",
                    actor_type="fixture",
                    decision_payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_trade",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=None,
                )
            )
            order = repository.create_order_record(
                OrderRecordCreate(
                    proposed_trade_id=proposed.id,
                    approval_id=approval.id,
                    status="recorded",
                    order_intent_payload={"schema_version": 1, "side": "buy"},
                    payload_schema_version=1,
                    broker_reference=None,
                    simulated_broker_reference=None,
                    correlation_id="corr_trade",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=None,
                )
            )
            fill = repository.create_fill_record(
                FillCreate(
                    order_id=order.id,
                    status="recorded",
                    quantity=Decimal("2"),
                    price=Decimal("225.50"),
                    broker_reference=None,
                    simulated_broker_reference=None,
                    payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_trade",
                    occurred_at=created_at,
                    created_at=created_at,
                )
            )
            position = repository.create_position_record(
                PositionCreate(
                    symbol_id=symbol.id,
                    instrument_id=None,
                    status="open",
                    quantity=Decimal("2"),
                    average_price=Decimal("225.50"),
                    payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_trade",
                    created_at=created_at,
                    updated_at=created_at,
                    closed_at=None,
                )
            )
            session.commit()

        with Session(engine) as session:
            repository = TradeLifecycleRepository(session)
            stored = (
                repository.get_proposed_trade(proposed.id),
                repository.get_approval(approval.id),
                repository.get_order(order.id),
                repository.get_fill(fill.id),
                repository.get_position(position.id),
            )
            events = AuditRepository(session).list_by_correlation_id("corr_trade")

        assert stored == (proposed, approval, order, fill, position)
        assert order.broker_reference is None
        assert order.simulated_broker_reference is None
        assert fill.broker_reference is None
        assert {record.correlation_id for record in stored if record is not None} == {
            "corr_trade"
        }
        assert len(events) == 5
    finally:
        engine.dispose()


def test_updates_lifecycle_statuses_with_audit_events(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    created_at = utc_now()
    updated_at = utc_now()
    try:
        with Session(engine) as session:
            repository = TradeLifecycleRepository(session)
            proposed = repository.create_proposed_trade(
                ProposedTradeCreate(
                    candidate_id=None,
                    status="pending",
                    order_intent_payload={"schema_version": 1, "side": "buy"},
                    payload_schema_version=1,
                    correlation_id="corr_update",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=None,
                )
            )
            approval = repository.create_approval(
                ApprovalCreate(
                    proposed_trade_id=proposed.id,
                    status="pending",
                    actor_type="operator",
                    decision_payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_update",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=None,
                )
            )
            order = repository.create_order_record(
                OrderRecordCreate(
                    proposed_trade_id=proposed.id,
                    approval_id=approval.id,
                    status="accepted",
                    order_intent_payload={"schema_version": 1, "side": "buy"},
                    payload_schema_version=1,
                    broker_reference=None,
                    simulated_broker_reference=None,
                    correlation_id="corr_update",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=None,
                )
            )

            updated_proposed = repository.update_proposed_trade_status(
                proposed.id,
                status="approved",
                updated_at=updated_at,
                terminal_at=None,
                correlation_id="corr_update",
            )
            updated_approval = repository.update_approval_status(
                approval.id,
                status="approved",
                updated_at=updated_at,
                terminal_at=updated_at,
                correlation_id="corr_update",
            )
            updated_order = repository.update_order_status(
                order.id,
                status="working",
                updated_at=updated_at,
                terminal_at=None,
                correlation_id="corr_update",
                simulated_broker_reference="paper-order-1",
            )
            session.commit()

        with Session(engine) as session:
            events = AuditRepository(session).list_by_correlation_id("corr_update")

        assert updated_proposed is not None
        assert updated_proposed.status == "approved"
        assert updated_proposed.updated_at == updated_at
        assert updated_approval is not None
        assert updated_approval.status == "approved"
        assert updated_approval.terminal_at == updated_at
        assert updated_order is not None
        assert updated_order.status == "working"
        assert updated_order.broker_reference is None
        assert updated_order.simulated_broker_reference == "paper-order-1"
        assert {event.event_type for event in events} >= {
            "proposed_trade.status_updated",
            "approval.status_updated",
            "order.status_updated",
        }
    finally:
        engine.dispose()


def test_lists_orders_fills_and_open_positions_for_recovery(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    created_at = utc_now()
    try:
        with Session(engine) as session:
            symbol = SymbolRepository(session).create_symbol(
                SymbolCreate(
                    display_symbol="SPY",
                    instrument_type="equity",
                    exchange=None,
                    is_active=True,
                    first_observed_at=created_at,
                    last_observed_at=created_at,
                    metadata_payload={"schema_version": 1},
                    metadata_schema_version=1,
                    correlation_id="corr_recovery",
                )
            )
            repository = TradeLifecycleRepository(session)
            working_order = repository.create_order_record(
                OrderRecordCreate(
                    proposed_trade_id=None,
                    approval_id=None,
                    status="working",
                    order_intent_payload={"schema_version": 1, "side": "buy"},
                    payload_schema_version=1,
                    broker_reference=None,
                    simulated_broker_reference="paper-working",
                    correlation_id="corr_recovery",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=None,
                )
            )
            filled_order = repository.create_order_record(
                OrderRecordCreate(
                    proposed_trade_id=None,
                    approval_id=None,
                    status="filled",
                    order_intent_payload={"schema_version": 1, "side": "buy"},
                    payload_schema_version=1,
                    broker_reference=None,
                    simulated_broker_reference="paper-filled",
                    correlation_id="corr_recovery",
                    created_at=created_at,
                    updated_at=created_at,
                    terminal_at=created_at,
                )
            )
            fill = repository.create_fill_record(
                FillCreate(
                    order_id=working_order.id,
                    status="recorded",
                    quantity=Decimal("1"),
                    price=Decimal("502.10"),
                    broker_reference=None,
                    simulated_broker_reference="paper-fill-1",
                    payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_recovery",
                    occurred_at=created_at,
                    created_at=created_at,
                )
            )
            open_position = repository.create_position_record(
                PositionCreate(
                    symbol_id=symbol.id,
                    instrument_id=None,
                    status="open",
                    quantity=Decimal("1"),
                    average_price=Decimal("502.10"),
                    payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_recovery",
                    created_at=created_at,
                    updated_at=created_at,
                    closed_at=None,
                )
            )
            repository.create_position_record(
                PositionCreate(
                    symbol_id=symbol.id,
                    instrument_id=None,
                    status="closed",
                    quantity=Decimal("0"),
                    average_price=Decimal("501.00"),
                    payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_recovery",
                    created_at=created_at,
                    updated_at=created_at,
                    closed_at=created_at,
                )
            )
            session.commit()

        with Session(engine) as session:
            repository = TradeLifecycleRepository(session)
            recoverable_orders = repository.list_orders_by_status({"accepted", "working"})
            fills = repository.list_fills_for_order(working_order.id)
            open_positions = repository.list_positions_by_status({"open", "partially_closed"})

        assert recoverable_orders == (working_order,)
        assert fills == (fill,)
        assert open_positions == (open_position,)
        assert filled_order not in recoverable_orders
    finally:
        engine.dispose()
