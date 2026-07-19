from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.db.models import CandidateORM, SignalORM
from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.decisions import (
    CandidateCreate,
    DecisionRepository,
    SignalCreate,
)
from market_trader.repositories.market_data import (
    MarketDataRepository,
    MarketDataSnapshotCreate,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from tests.db_helpers import migrated_engine


def test_creates_signal_and_candidate_from_snapshot_with_shared_correlation(
    tmp_path: Path,
) -> None:
    engine = migrated_engine(tmp_path)
    created_at = utc_now()
    try:
        with Session(engine) as session:
            symbol = SymbolRepository(session).create_symbol(
                SymbolCreate(
                    display_symbol="QQQ",
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
            snapshot = MarketDataRepository(session).store_snapshot(
                MarketDataSnapshotCreate(
                    source="fixture",
                    symbol_id=symbol.id,
                    instrument_id=None,
                    observed_at=created_at,
                    ingested_at=created_at,
                    session_date=None,
                    quality_state="valid",
                    configuration_version_id=None,
                    payload={"schema_version": 1, "last": "550.00"},
                    payload_schema_version=1,
                    correlation_id="corr_decision",
                )
            )
            repository = DecisionRepository(session)
            signal = repository.create_signal(
                SignalCreate(
                    strategy_version="fixture-v1",
                    symbol_id=symbol.id,
                    instrument_id=None,
                    direction="long",
                    score=Decimal("87.5"),
                    status="observed",
                    input_snapshot_id=snapshot.id,
                    explanation_payload={"schema_version": 1, "rule": "fixture"},
                    explanation_schema_version=1,
                    correlation_id="corr_decision",
                    created_at=created_at,
                )
            )
            candidate = repository.create_candidate(
                CandidateCreate(
                    signal_id=signal.id,
                    symbol_id=symbol.id,
                    instrument_id=None,
                    status="stored",
                    score=Decimal("87.5"),
                    explanation_payload={"schema_version": 1, "reason": "fixture"},
                    explanation_schema_version=1,
                    correlation_id="corr_decision",
                    created_at=created_at,
                )
            )
            session.commit()

        with Session(engine) as session:
            stored = DecisionRepository(session).get_candidate(candidate.id)
            events = AuditRepository(session).list_by_correlation_id("corr_decision")
            signal_record = session.get(SignalORM, signal.id)
            candidate_record = session.get(CandidateORM, candidate.id)

        assert stored == candidate
        assert stored is not None
        assert stored.explanation_payload["reason"] == "fixture"
        assert stored.correlation_id == "corr_decision"
        assert {event.event_type for event in events} == {
            "market_data_snapshot.stored",
            "signal.created",
            "candidate.created",
        }
        assert signal_record is not None and signal_record.scanner_run_id is None
        assert candidate_record is not None and candidate_record.scanner_run_id is None
    finally:
        engine.dispose()
