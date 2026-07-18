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
