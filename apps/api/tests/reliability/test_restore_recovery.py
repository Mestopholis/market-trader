from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from market_trader.db.backup import backup_sqlite_database
from market_trader.db.engine import create_engine_from_url
from market_trader.recovery.restore import restore_backup_with_validation
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.orders import (
    ApprovalCreate,
    FillCreate,
    OrderRecordCreate,
    PositionCreate,
    ProposedTradeCreate,
    TradeLifecycleRepository,
)
from market_trader.repositories.risk_locks import RiskLockCreate, RiskLockRepository
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_restore_validation_preserves_paper_audit_state_and_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    engine = migrated_engine(tmp_path, source.name)
    try:
        _seed_recoverable_state(engine)
    finally:
        engine.dispose()

    metadata = backup_sqlite_database(
        source,
        backup,
        correlation_id="corr-backup-restore-drill",
    )

    report = restore_backup_with_validation(
        backup,
        restored,
        expected_metadata=metadata,
        correlation_id="corr-restore-drill",
    )

    assert report.integrity_ok is True
    assert report.backup_sha256 == metadata.sha256
    assert report.row_counts["approvals"] == 1
    assert report.row_counts["orders"] == 1
    assert report.row_counts["fills"] == 1
    assert report.row_counts["positions"] == 1
    assert report.row_counts["risk_locks"] == 1
    assert report.row_counts["journal_events"] == metadata.row_counts["journal_events"] + 1

    restored_engine = create_engine_from_url(f"sqlite:///{restored}")
    try:
        with Session(restored_engine) as session:
            events = AuditRepository(session).list_by_correlation_id("corr-restore-drill")

        assert [event.event_type for event in events] == ["recovery.restore_validated"]
        assert events[0].id == report.recovery_event_id
        assert events[0].payload["row_counts"]["orders"] == 1
        assert events[0].payload["validated_tables"] == [
            "journal_events",
            "proposed_trades",
            "approvals",
            "orders",
            "fills",
            "positions",
            "risk_locks",
        ]
    finally:
        restored_engine.dispose()


def _seed_recoverable_state(engine: Engine) -> None:
    with Session(engine) as session:
        symbol = SymbolRepository(session).create_symbol(
            SymbolCreate(
                display_symbol="SPY",
                instrument_type="equity",
                exchange=None,
                is_active=True,
                first_observed_at=AS_OF,
                last_observed_at=AS_OF,
                metadata_payload={"schema_version": 1},
                metadata_schema_version=1,
                correlation_id="corr-restore-source",
            )
        )
        lifecycle = TradeLifecycleRepository(session)
        proposed = lifecycle.create_proposed_trade(
            ProposedTradeCreate(
                candidate_id=None,
                status="approved",
                order_intent_payload={"schema_version": 1},
                payload_schema_version=1,
                correlation_id="corr-restore-source",
                created_at=AS_OF,
                updated_at=AS_OF,
                terminal_at=None,
            )
        )
        approval = lifecycle.create_approval(
            ApprovalCreate(
                proposed_trade_id=proposed.id,
                status="approved",
                actor_type="operator",
                decision_payload={"schema_version": 1},
                payload_schema_version=1,
                correlation_id="corr-restore-source",
                created_at=AS_OF,
                updated_at=AS_OF,
                terminal_at=None,
            )
        )
        order = lifecycle.create_order_record(
            OrderRecordCreate(
                proposed_trade_id=proposed.id,
                approval_id=approval.id,
                status="working",
                order_intent_payload={"schema_version": 1},
                payload_schema_version=1,
                broker_reference=None,
                simulated_broker_reference="sim-restore-order",
                correlation_id="corr-restore-source",
                created_at=AS_OF,
                updated_at=AS_OF,
                terminal_at=None,
            )
        )
        lifecycle.create_fill_record(
            FillCreate(
                order_id=order.id,
                status="recorded",
                quantity=Decimal("1"),
                price=Decimal("500.00"),
                broker_reference=None,
                simulated_broker_reference="sim-restore-fill",
                payload={"schema_version": 1},
                payload_schema_version=1,
                correlation_id="corr-restore-source",
                occurred_at=AS_OF,
                created_at=AS_OF,
            )
        )
        lifecycle.create_position_record(
            PositionCreate(
                symbol_id=symbol.id,
                instrument_id=None,
                status="open",
                quantity=Decimal("1"),
                average_price=Decimal("500.00"),
                payload={"schema_version": 1},
                payload_schema_version=1,
                correlation_id="corr-restore-source",
                created_at=AS_OF,
                updated_at=AS_OF,
                closed_at=None,
            )
        )
        RiskLockRepository(session).create(
            RiskLockCreate(
                lock_type="manual_review",
                status="active",
                reason="restore drill fixture",
                source_event_id=None,
                activated_at=AS_OF,
                payload={"schema_version": 1},
                payload_schema_version=1,
                correlation_id="corr-restore-source",
            )
        )
        session.commit()
