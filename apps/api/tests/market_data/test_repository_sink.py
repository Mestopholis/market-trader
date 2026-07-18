from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_trader.db.models import (
    JournalEventORM,
    MarketDataQuarantineORM,
    MarketDataSnapshotORM,
)
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.fixtures import FixtureDataset
from market_trader.market_data.replay import ReplayEngine, VirtualReplayClock
from market_trader.market_data.sinks import ReplayInfrastructureError, RepositoryIngestionSink
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.market_data import (
    IngestionConflictError,
    MarketDataQuarantineCreate,
    MarketDataRepository,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from tests.db_helpers import migrated_engine

FIXTURE = Path(__file__).parent / "fixtures" / "minimal"
OBSERVED = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)


def test_quarantine_is_idempotent_and_audited_once(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    command = quarantine_command()
    try:
        with Session(engine) as session:
            repository = MarketDataRepository(session)
            first = repository.quarantine(command)
            second = repository.quarantine(command)
            events = AuditRepository(session).list_by_subject(
                "market_data_quarantine",
                first.id,
            )
            session.commit()

        assert first == second
        assert len(events) == 1
        assert events[0].event_type == "market_data_observation.quarantined"
        assert first.sanitized_payload == {"Authorization": "[REDACTED]"}
    finally:
        engine.dispose()


def test_quarantine_conflict_does_not_overwrite_existing_record(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            repository = MarketDataRepository(session)
            repository.quarantine(quarantine_command())
            with pytest.raises(IngestionConflictError, match="ing_quarantine_1"):
                repository.quarantine(
                    quarantine_command(payload_digest="different-digest")
                )
    finally:
        engine.dispose()


def test_quarantine_and_audit_roll_back_together(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            stored = MarketDataRepository(session).quarantine(quarantine_command())
            session.rollback()

        with Session(engine) as session:
            assert (
                MarketDataRepository(session).get_quarantine_by_ingestion_key(
                    "ing_quarantine_1"
                )
                is None
            )
            assert AuditRepository(session).list_by_subject(
                "market_data_quarantine", stored.id
            ) == []
    finally:
        engine.dispose()


def test_repository_sink_replay_is_idempotent(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    dataset = FixtureDataset.load(FIXTURE)
    calendar = XNYSCalendarAdapter(start=OBSERVED.date(), end=OBSERVED.date().replace(year=2027))
    try:
        with Session(engine) as session:
            create_symbol(session, "SPY")
            first = ReplayEngine(
                clock=VirtualReplayClock(),
                calendar=calendar,
                sink=RepositoryIngestionSink(session),
            ).replay(dataset)
            second = ReplayEngine(
                clock=VirtualReplayClock(),
                calendar=calendar,
                sink=RepositoryIngestionSink(session),
            ).replay(dataset)
            session.commit()

        with Session(engine) as session:
            snapshot_count = session.scalar(select(func.count()).select_from(MarketDataSnapshotORM))
            quarantine_count = session.scalar(
                select(func.count()).select_from(MarketDataQuarantineORM)
            )
            audit_count = session.scalar(select(func.count()).select_from(JournalEventORM))

        assert first.accepted == 2
        assert second.deduplicated == 2
        assert snapshot_count == 2
        assert quarantine_count == 0
        assert audit_count == 3  # Symbol creation plus two snapshot events.
    finally:
        engine.dispose()


def test_repository_sink_rejects_unknown_symbol(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    dataset = FixtureDataset.load(FIXTURE)
    calendar = XNYSCalendarAdapter(start=OBSERVED.date(), end=OBSERVED.date().replace(year=2027))
    try:
        with Session(engine) as session:
            with pytest.raises(ReplayInfrastructureError, match="unknown symbol: SPY"):
                ReplayEngine(
                    clock=VirtualReplayClock(),
                    calendar=calendar,
                    sink=RepositoryIngestionSink(session),
                ).replay(dataset)
            session.rollback()
    finally:
        engine.dispose()


def quarantine_command(
    *, payload_digest: str = "digest_quarantine_1"
) -> MarketDataQuarantineCreate:
    return MarketDataQuarantineCreate(
        ingestion_key="ing_quarantine_1",
        source="fixture",
        event_id="event-1",
        data_kind="quote",
        observed_at=OBSERVED,
        ingested_at=OBSERVED,
        symbol_identity="SPY",
        instrument_identity=None,
        sanitized_payload={"Authorization": "[REDACTED]"},
        payload_digest=payload_digest,
        reason_codes=("missing_field",),
        fixture_schema_version=1,
        normalized_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id="corr-quarantine",
    )


def create_symbol(session: Session, display_symbol: str) -> None:
    SymbolRepository(session).create_symbol(
        SymbolCreate(
            display_symbol=display_symbol,
            instrument_type="equity",
            exchange="ARCX",
            is_active=True,
            first_observed_at=OBSERVED,
            last_observed_at=OBSERVED,
            metadata_payload={"schema_version": 1},
            metadata_schema_version=1,
            correlation_id="corr-symbol",
        )
    )
