from datetime import UTC, date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.domain.time import utc_now
from market_trader.repositories.market_data import (
    MarketDataRepository,
    MarketDataSnapshotCreate,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from tests.db_helpers import migrated_engine


def test_stores_and_lists_snapshots_by_symbol_source_and_time(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    observed_at = utc_now()
    try:
        with Session(engine) as session:
            symbol = SymbolRepository(session).create_symbol(
                SymbolCreate(
                    display_symbol="SPY",
                    instrument_type="equity",
                    exchange="ARCX",
                    is_active=True,
                    first_observed_at=observed_at,
                    last_observed_at=observed_at,
                    metadata_payload={"schema_version": 1},
                    metadata_schema_version=1,
                    correlation_id="corr_setup",
                )
            )
            snapshot = MarketDataRepository(session).store_snapshot(
                MarketDataSnapshotCreate(
                    source="fixture",
                    symbol_id=symbol.id,
                    instrument_id=None,
                    observed_at=observed_at,
                    ingested_at=observed_at,
                    session_date=date(2026, 7, 17),
                    quality_state="valid",
                    configuration_version_id=None,
                    payload={"schema_version": 1, "last": "625.50"},
                    payload_schema_version=1,
                    correlation_id="corr_pipeline",
                )
            )
            session.commit()

        with Session(engine) as session:
            stored = MarketDataRepository(session).list_snapshots(
                symbol_id=symbol.id,
                source="fixture",
                observed_from=observed_at - timedelta(seconds=1),
                observed_to=observed_at + timedelta(seconds=1),
            )

        assert stored == [snapshot]
        assert stored[0].observed_at.tzinfo is UTC
        assert stored[0].payload == {"schema_version": 1, "last": "625.50"}
    finally:
        engine.dispose()
