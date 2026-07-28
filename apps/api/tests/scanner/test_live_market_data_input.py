from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.repositories.market_data import (
    MarketDataRepository,
    MarketDataSnapshotCreate,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.live_input import build_scanner_input_from_market_data
from tests.db_helpers import migrated_engine

NOW = datetime(2026, 7, 28, 15, 30, tzinfo=UTC)


def test_builds_scanner_input_from_recent_schwab_quote_snapshot(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session, session.begin():
            symbol_id = _create_symbol(session, "SPY")
            MarketDataRepository(session).store_snapshot(
                MarketDataSnapshotCreate(
                    ingestion_key="schwab:quote:SPY:1",
                    payload_digest="a" * 64,
                    event_id="schwab-quote-event",
                    source="schwab",
                    data_kind="quote",
                    symbol_id=symbol_id,
                    instrument_id=None,
                    observed_at=NOW,
                    ingested_at=NOW + timedelta(seconds=1),
                    session_date=None,
                    quality_state="valid",
                    reason_codes=(),
                    configuration_version_id=None,
                    payload=_quote_payload("SPY"),
                    payload_schema_version=1,
                    correlation_id="corr-live-scanner",
                )
            )
            configuration = load_scanner_configuration(Path("config/scanner"))

            scanner_input = build_scanner_input_from_market_data(
                session,
                configuration=configuration,
                as_of=NOW + timedelta(seconds=2),
                observed_from=NOW - timedelta(minutes=15),
                source="schwab",
            )

        spy = next(symbol for symbol in scanner_input.symbols if symbol.symbol == "SPY")
        assert scanner_input.as_of == NOW + timedelta(seconds=2)
        assert scanner_input.versions == configuration.versions
        assert dict(scanner_input.configuration_hashes) == dict(configuration.content_hashes)
        assert len(spy.quotes) == 1
        assert spy.quotes[0].symbol == "SPY"
        assert spy.quotes[0].bid == Decimal("625.10")
        assert spy.attributes["quote_updating"] is True
        assert spy.attributes["symbol_active"] is True
        assert spy.evidence[0].ingestion_key == "schwab:quote:SPY:1"
        assert spy.evidence[0].payload_digest == "a" * 64
    finally:
        engine.dispose()


def _create_symbol(session: Session, display_symbol: str) -> str:
    return SymbolRepository(session).create_symbol(
        SymbolCreate(
            display_symbol=display_symbol,
            instrument_type="equity",
            exchange="ARCX",
            is_active=True,
            first_observed_at=NOW,
            last_observed_at=NOW,
            metadata_payload={"schema_version": 1},
            metadata_schema_version=1,
            correlation_id="corr-symbol",
        )
    ).id


def _quote_payload(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "bid": "625.10",
        "ask": "625.20",
        "bid_size": 100,
        "ask_size": 200,
        "last": "625.15",
        "last_size": 25,
        "last_at": NOW.isoformat(),
        "bid_venue": "XNYS",
        "ask_venue": "ARCX",
        "trade_venue": "XNAS",
        "condition_codes": [],
        "metadata": {
            "source": "schwab",
            "event_id": "schwab-quote-event",
            "observed_at": NOW.isoformat(),
            "ingested_at": (NOW + timedelta(seconds=1)).isoformat(),
            "session_date": None,
            "normalized_schema_version": 1,
            "configuration_version": "schwab-market-data-v1",
            "correlation_id": "corr-live-scanner",
            "quality_state": "valid",
            "quality_reasons": [],
        },
    }
