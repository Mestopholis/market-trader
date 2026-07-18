from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from market_trader.db.session import session_scope
from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.symbols import (
    InstrumentCreate,
    SymbolCreate,
    SymbolRepository,
)
from tests.db_helpers import migrated_engine


def test_creates_and_fetches_symbol_and_instrument_with_audit_events(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    observed_at = utc_now()
    try:
        with Session(engine) as session:
            repository = SymbolRepository(session)
            symbol = repository.create_symbol(
                SymbolCreate(
                    display_symbol="SPY",
                    instrument_type="equity",
                    exchange="ARCX",
                    is_active=True,
                    first_observed_at=observed_at,
                    last_observed_at=observed_at,
                    metadata_payload={"schema_version": 1, "name": "SPDR S&P 500 ETF Trust"},
                    metadata_schema_version=1,
                    correlation_id="corr_symbols",
                )
            )
            instrument = repository.create_instrument(
                InstrumentCreate(
                    symbol_id=symbol.id,
                    instrument_type="equity",
                    exchange="ARCX",
                    external_reference=None,
                    is_active=True,
                    first_observed_at=observed_at,
                    last_observed_at=observed_at,
                    metadata_payload={"schema_version": 1},
                    metadata_schema_version=1,
                    correlation_id="corr_symbols",
                )
            )
            session.commit()

        with Session(engine) as session:
            repository = SymbolRepository(session)
            stored_symbol = repository.get_symbol_by_display_symbol("SPY")
            stored_instruments = repository.get_instruments_for_symbol(symbol.id)
            events = AuditRepository(session).list_by_correlation_id("corr_symbols")

        assert stored_symbol == symbol
        assert stored_symbol is not None
        assert stored_symbol.first_observed_at.tzinfo is UTC
        assert stored_instruments == [instrument]
        assert [event.event_type for event in events] == [
            "symbol.created",
            "instrument.created",
        ]
    finally:
        engine.dispose()


def test_audited_symbol_write_rolls_back_as_one_transaction(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    observed_at = utc_now()
    try:
        with pytest.raises(RuntimeError, match="force rollback"), session_scope(engine) as session:
            SymbolRepository(session).create_symbol(
                SymbolCreate(
                    display_symbol="QQQ",
                    instrument_type="equity",
                    exchange=None,
                    is_active=True,
                    first_observed_at=observed_at,
                    last_observed_at=observed_at,
                    metadata_payload={"schema_version": 1},
                    metadata_schema_version=1,
                    correlation_id="corr_rollback",
                )
            )
            raise RuntimeError("force rollback")

        with Session(engine) as session:
            assert SymbolRepository(session).get_symbol_by_display_symbol("QQQ") is None
            assert AuditRepository(session).list_by_correlation_id("corr_rollback") == []
    finally:
        engine.dispose()
