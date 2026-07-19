from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from market_trader.db.models import (
    CandidateORM,
    EligibilityDecisionORM,
    ScannerRunORM,
    SignalORM,
)
from market_trader.repositories.audit import AuditEvent, AuditEventCreate, AuditRepository
from market_trader.repositories.market_data import (
    MarketDataRepository,
    MarketDataSnapshotCreate,
)
from market_trader.repositories.scanner import (
    ScannerPersistenceConflict,
    ScannerPersistenceError,
    ScannerRepository,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from market_trader.scanner.models import (
    CandidateResult,
    ComponentScore,
    Direction,
    EligibilityResult,
    EligibilityStatus,
    EvidenceRef,
    GateResult,
    PolicyVersions,
    RegimeResult,
    RegimeState,
    ScanCounts,
    ScanResult,
    StrategyResult,
    StrategyStatus,
)
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)
SYMBOLS = ("SPY", *(f"SYM{index:02d}" for index in range(1, 30)))
INGESTION_KEY = "fixture:SPY:primary"


def test_persists_complete_scan_and_audits_in_one_transaction(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    result = _scan_result()
    try:
        _seed_inputs(engine)
        with Session(engine) as session, session.begin():
            persisted = ScannerRepository(session).persist(result)

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ScannerRunORM)) == 1
            assert session.scalar(select(func.count()).select_from(EligibilityDecisionORM)) == 30
            assert session.scalar(select(func.count()).select_from(SignalORM)) == 5
            assert session.scalar(select(func.count()).select_from(CandidateORM)) == 1
            stored_run = session.scalar(select(ScannerRunORM))
            events = AuditRepository(session).list_by_correlation_id(persisted.correlation_id)

        assert persisted.run_key == result.run_key
        assert stored_run is not None
        assert stored_run.universe_content_hash == "u" * 64
        assert stored_run.input_digest == result.input_digest
        assert stored_run.result_digest == result.result_digest
        assert [event.event_type for event in events].count("scanner_run.completed") == 1
        assert [event.event_type for event in events].count("eligibility_decision.recorded") == 30
        assert [event.event_type for event in events].count("scanner_signal.recorded") == 5
        assert [event.event_type for event in events].count("scanner_candidate.qualified") == 1
    finally:
        engine.dispose()


def test_exact_rerun_returns_existing_result_without_duplicates(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    result = _scan_result()
    try:
        _seed_inputs(engine)
        with Session(engine) as session, session.begin():
            first = ScannerRepository(session).persist(result)
        with Session(engine) as session, session.begin():
            second = ScannerRepository(session).persist(result)

        with Session(engine) as session:
            event_count = len(AuditRepository(session).list_by_correlation_id(first.correlation_id))
            run_count = session.scalar(select(func.count()).select_from(ScannerRunORM))

        assert second == first
        assert run_count == 1
        assert event_count == 37
    finally:
        engine.dispose()


def test_same_run_key_with_changed_digest_is_a_conflict(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    result = _scan_result()
    try:
        _seed_inputs(engine)
        with Session(engine) as session, session.begin():
            ScannerRepository(session).persist(result)

        changed = replace(result, input_digest="x" * 64)
        with (
            Session(engine) as session,
            pytest.raises(ScannerPersistenceConflict, match="run key conflict"),
            session.begin(),
        ):
            ScannerRepository(session).persist(changed)

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ScannerRunORM)) == 1
            assert session.scalar(select(func.count()).select_from(EligibilityDecisionORM)) == 30
    finally:
        engine.dispose()


@pytest.mark.parametrize("missing", ["symbol", "snapshot"])
def test_missing_input_reference_rolls_back_entire_run(tmp_path: Path, missing: str) -> None:
    engine = migrated_engine(tmp_path)
    result = _scan_result()
    try:
        _seed_inputs(
            engine,
            omit_symbol="SYM29" if missing == "symbol" else None,
            include_snapshot=missing != "snapshot",
        )
        with (
            Session(engine) as session,
            pytest.raises(ScannerPersistenceError, match=missing),
            session.begin(),
        ):
            ScannerRepository(session).persist(result)

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ScannerRunORM)) == 0
            assert session.scalar(select(func.count()).select_from(EligibilityDecisionORM)) == 0
            assert session.scalar(select(func.count()).select_from(SignalORM)) == 0
    finally:
        engine.dispose()


def test_audit_failure_rolls_back_run_and_all_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = migrated_engine(tmp_path)
    result = _scan_result()
    try:
        _seed_inputs(engine)
        original_append = AuditRepository.append
        calls = 0

        def fail_after_first_audit(
            repository: AuditRepository, event: AuditEventCreate
        ) -> AuditEvent:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected audit failure")
            return original_append(repository, event)

        monkeypatch.setattr(AuditRepository, "append", fail_after_first_audit)
        with (
            Session(engine) as session,
            pytest.raises(RuntimeError, match="injected audit failure"),
            session.begin(),
        ):
            ScannerRepository(session).persist(result)

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ScannerRunORM)) == 0
            assert session.scalar(select(func.count()).select_from(EligibilityDecisionORM)) == 0
            assert session.scalar(select(func.count()).select_from(SignalORM)) == 0
            assert session.scalar(select(func.count()).select_from(CandidateORM)) == 0
    finally:
        engine.dispose()


def test_flush_failure_rolls_back_run_and_all_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = migrated_engine(tmp_path)
    result = _scan_result()
    try:
        _seed_inputs(engine)
        original_flush = Session.flush
        calls = 0

        def fail_after_partial_write(session: Session, objects: Any | None = None) -> None:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("injected flush failure")
            original_flush(session, objects)

        monkeypatch.setattr(Session, "flush", fail_after_partial_write)
        with (
            Session(engine) as session,
            pytest.raises(RuntimeError, match="injected flush failure"),
            session.begin(),
        ):
            ScannerRepository(session).persist(result)

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ScannerRunORM)) == 0
            assert session.scalar(select(func.count()).select_from(EligibilityDecisionORM)) == 0
            assert session.scalar(select(func.count()).select_from(SignalORM)) == 0
            assert session.scalar(select(func.count()).select_from(CandidateORM)) == 0
    finally:
        engine.dispose()


def _seed_inputs(
    engine: Engine,
    *,
    omit_symbol: str | None = None,
    include_snapshot: bool = True,
) -> None:
    with Session(engine) as session, session.begin():
        symbols = SymbolRepository(session)
        stored = {}
        for display_symbol in SYMBOLS:
            if display_symbol == omit_symbol:
                continue
            stored[display_symbol] = symbols.create_symbol(
                SymbolCreate(
                    display_symbol=display_symbol,
                    instrument_type="equity",
                    exchange="XNYS",
                    is_active=True,
                    first_observed_at=AS_OF,
                    last_observed_at=AS_OF,
                    metadata_payload={"schema_version": 1},
                    metadata_schema_version=1,
                    correlation_id="seed",
                )
            )
        if include_snapshot:
            MarketDataRepository(session).store_snapshot(
                MarketDataSnapshotCreate(
                    ingestion_key=INGESTION_KEY,
                    payload_digest="p" * 64,
                    source="fixture",
                    data_kind="quote",
                    symbol_id=stored["SPY"].id,
                    instrument_id=None,
                    observed_at=AS_OF - timedelta(minutes=1),
                    ingested_at=AS_OF - timedelta(seconds=30),
                    session_date=date(2026, 7, 17),
                    quality_state="valid",
                    configuration_version_id=None,
                    payload={"schema_version": 1, "last": "650.00"},
                    payload_schema_version=1,
                    correlation_id="seed",
                )
            )


def _scan_result() -> ScanResult:
    versions = PolicyVersions()
    eligibility = tuple(
        EligibilityResult(
            symbol=symbol,
            status=(
                EligibilityStatus.ELIGIBLE if symbol == "SPY" else EligibilityStatus.INELIGIBLE
            ),
            policy_version=versions.eligibility,
            reasons=() if symbol == "SPY" else ("inactive_fixture",),
            observed={"symbol_active": symbol == "SPY"},
        )
        for symbol in SYMBOLS
    )
    reference = EvidenceRef(
        lineage_id="lineage-SPY",
        source="fixture",
        event_id="event-SPY",
        ingestion_key=INGESTION_KEY,
        payload_digest="p" * 64,
        observed_at=AS_OF - timedelta(minutes=1),
        ingested_at=AS_OF - timedelta(seconds=30),
    )
    strategy_ids = (
        "bullish_breakout",
        "bullish_pullback",
        "bearish_breakdown",
        "bearish_failed_rally",
        "news_continuation",
    )
    strategies = tuple(
        StrategyResult(
            signal_key=f"scan-key:SPY:{strategy_id}:{versions.strategies}",
            symbol="SPY",
            strategy_id=strategy_id,
            policy_version=versions.strategies,
            direction=(Direction.BEARISH if "bearish" in strategy_id else Direction.BULLISH),
            status=(StrategyStatus.PASSED if index == 0 else StrategyStatus.FAILED),
            gates=(GateResult(name="fixture", passed=index == 0),),
            components=(
                ComponentScore(
                    family="fixture",
                    pre_cap=Decimal("80" if index == 0 else "10"),
                    cap=Decimal("100"),
                    final=Decimal("80" if index == 0 else "10"),
                    lineage=("lineage-SPY",),
                ),
            ),
            reasons=() if index == 0 else ("fixture_gate_failed",),
            lineage=("lineage-SPY",),
            input_references=(reference,),
            primary_ingestion_key=INGESTION_KEY,
            input_digest="i" * 64,
            score=Decimal("80" if index == 0 else "10"),
        )
        for index, strategy_id in enumerate(strategy_ids)
    )
    candidate = CandidateResult(
        candidate_key=f"{strategies[0].signal_key}:{versions.scoring}",
        signal_key=strategies[0].signal_key,
        symbol="SPY",
        strategy_id=strategies[0].strategy_id,
        direction=Direction.BULLISH,
        score=Decimal("80"),
        input_digest="i" * 64,
    )
    return ScanResult(
        run_key="scan-key",
        as_of=AS_OF,
        session_date=date(2026, 7, 17),
        versions=versions,
        input_digest="i" * 64,
        regime=RegimeResult(
            state=RegimeState.BULLISH,
            signed_score=Decimal("0.500000"),
            policy_version=versions.regime,
            components={"fixture": Decimal("0.500000")},
            reasons=("fixture_regime",),
            lineage=("lineage-SPY",),
        ),
        eligibility=eligibility,
        strategies=strategies,
        candidates=(candidate,),
        counts=ScanCounts(eligible=1, ineligible=29, signals=5, candidates=1),
        result_digest="r" * 64,
        configuration_hashes={"universe": "u" * 64},
    )
