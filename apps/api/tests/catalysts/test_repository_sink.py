from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from market_trader.catalysts.models import (
    AuthorityClass,
    CatalystDecision,
    CatalystDirection,
    CatalystObservation,
    CatalystPolicyVersions,
    CitedSummary,
    ConfirmationState,
    EventFamily,
    Materiality,
    QuarantinedObservation,
    RiskState,
    SourceRunResult,
    SourceState,
    SummarySegment,
)
from market_trader.catalysts.sinks import (
    CatalystPersistenceError,
    RepositoryCatalystSink,
)
from market_trader.db.models import (
    CatalystDecisionORM,
    CatalystObservationORM,
    CatalystQuarantineORM,
    CatalystSourceRunORM,
    CatalystSummaryORM,
    JournalEventORM,
)
from market_trader.repositories.catalysts import (
    CatalystPersistenceConflict,
    CatalystRepository,
)
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from tests.db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)


def test_persists_complete_result_and_maps_every_domain_record(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    result = _result()
    try:
        _seed_symbol(engine)
        with Session(engine) as session, session.begin():
            persisted = RepositoryCatalystSink(session).persist(result)

        with Session(engine) as session:
            counts = _counts(session)
            repository = CatalystRepository(session)
            catalyst_audits = tuple(
                event
                for event in session.scalars(select(JournalEventORM))
                if event.event_type.startswith("catalyst_")
            )
            assert repository.get_source_run(result.run_key) == persisted
            assert repository.get_observation("obs-1") == result.observations[0]
            assert repository.get_quarantine("qua-1") == result.quarantined[0]
            assert repository.get_decision("dec-1") == result.decisions[0]
            assert repository.get_summary("sum-1") == result.summaries[0]

        assert counts == (1, 1, 1, 1, 1, 6)
        assert len(catalyst_audits) == 5
        assert "Recorded" not in str(tuple(event.payload for event in catalyst_audits))
    finally:
        engine.dispose()


def test_exact_rerun_is_idempotent_without_new_rows_or_audit(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    result = _result()
    try:
        _seed_symbol(engine)
        with Session(engine) as session, session.begin():
            first = RepositoryCatalystSink(session).persist(result)
        with Session(engine) as session, session.begin():
            second = RepositoryCatalystSink(session).persist(result)
        with Session(engine) as session:
            counts = _counts(session)

        assert second == first
        assert counts == (1, 1, 1, 1, 1, 6)
    finally:
        engine.dispose()


def test_display_text_change_is_duplicate_but_authoritative_change_conflicts(
    tmp_path: Path,
) -> None:
    engine = migrated_engine(tmp_path)
    result = _result()
    try:
        _seed_symbol(engine)
        with Session(engine) as session, session.begin():
            RepositoryCatalystSink(session).persist(result)
        display_only = replace(
            result.observations[0],
            external_text_digest="f" * 64,
            external_text={"headline": "Changed display text"},
        )
        with Session(engine) as session, session.begin():
            stored = CatalystRepository(session).record_observation(
                "run-row", display_only, "sym-aapl"
            )
        assert stored == result.observations[0]

        changed = replace(result.observations[0], authoritative_digest="0" * 64)
        with (
            Session(engine) as session,
            pytest.raises(CatalystPersistenceConflict, match="observation key conflict"),
            session.begin(),
        ):
            CatalystRepository(session).record_observation("run-row", changed, "sym-aapl")
    finally:
        engine.dispose()


def test_missing_summary_citation_rolls_back_everything(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    result = _result()
    bad_summary = replace(
        result.summaries[0],
        segments=(SummarySegment("Bad citation", ("obs-missing",), ("fixture://missing",)),),
    )
    try:
        _seed_symbol(engine)
        with (
            Session(engine) as session,
            pytest.raises(CatalystPersistenceError, match="missing observation citation"),
            session.begin(),
        ):
            RepositoryCatalystSink(session).persist(replace(result, summaries=(bad_summary,)))
        with Session(engine) as session:
            assert _counts(session) == (0, 0, 0, 0, 0, 1)
    finally:
        engine.dispose()


def test_unknown_symbol_fails_before_any_catalyst_write(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with (
            Session(engine) as session,
            pytest.raises(CatalystPersistenceError, match="missing symbol: AAPL"),
            session.begin(),
        ):
            RepositoryCatalystSink(session).persist(_result())
        with Session(engine) as session:
            assert _counts(session) == (0, 0, 0, 0, 0, 0)
    finally:
        engine.dispose()


@pytest.mark.parametrize("method", ("record_observation", "record_decision", "record_summary"))
def test_injected_failure_rolls_back_domain_and_audit_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    engine = migrated_engine(tmp_path)
    try:
        _seed_symbol(engine)

        def fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("injected persistence failure")

        monkeypatch.setattr(CatalystRepository, method, fail)
        with (
            Session(engine) as session,
            pytest.raises(RuntimeError, match="injected persistence failure"),
            session.begin(),
        ):
            RepositoryCatalystSink(session).persist(_result())
        with Session(engine) as session:
            assert _counts(session) == (0, 0, 0, 0, 0, 1)
    finally:
        engine.dispose()


def _counts(session: Session) -> tuple[int, ...]:
    models = (
        CatalystSourceRunORM,
        CatalystObservationORM,
        CatalystQuarantineORM,
        CatalystDecisionORM,
        CatalystSummaryORM,
        JournalEventORM,
    )
    return tuple(session.scalar(select(func.count()).select_from(model)) or 0 for model in models)


def _seed_symbol(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        SymbolRepository(session).create_symbol(
            SymbolCreate(
                display_symbol="AAPL",
                instrument_type="equity",
                exchange="XNAS",
                is_active=True,
                first_observed_at=AS_OF,
                last_observed_at=AS_OF,
                metadata_payload={},
                metadata_schema_version=1,
                correlation_id="seed",
            )
        )


def _result() -> SourceRunResult:
    observation = CatalystObservation(
        observation_key="obs-1",
        ingestion_key="ing-1",
        authoritative_digest="a" * 64,
        external_text_digest="b" * 64,
        source_id="recorded-company-news-v1",
        authority_class=AuthorityClass.AUTHORIZED_STRUCTURED,
        event_family=EventFamily.COMPANY_NEWS,
        event_category="regulatory_approval",
        provider_event_id="event-1",
        source_reference="fixture://event-1",
        symbol="AAPL",
        published_at=AS_OF,
        ingested_at=AS_OF,
        scheduled_for=None,
        valid_until=AS_OF + timedelta(days=1),
        structured_facts={"event_category": "regulatory_approval"},
        external_text={"headline": "Recorded"},
        source_schema_version=1,
        normalization_schema_version=1,
        configuration_version="catalyst-source-policy-v1",
        correlation_id="corr-run",
    )
    quarantine = QuarantinedObservation(
        ingestion_key="qua-1",
        sanitized_payload_digest="c" * 64,
        source_id="recorded-company-news-v1",
        provider_event_id="event-bad",
        published_at=AS_OF,
        ingested_at=AS_OF,
        reasons=("malformed_payload",),
        sanitized_payload={"safe": "value"},
        source_schema_version=1,
        normalization_schema_version=1,
        correlation_id="corr-run",
    )
    decision = CatalystDecision(
        decision_key="dec-1",
        scope="symbol",
        symbol="AAPL",
        as_of=AS_OF,
        materiality=Materiality.MATERIAL,
        direction=CatalystDirection.POSITIVE,
        confirmation=ConfirmationState.CONFIRMED,
        risk_state=RiskState.CLEAR,
        reasons=(),
        observation_keys=("obs-1",),
        policy_versions=CatalystPolicyVersions(),
        input_digest="d" * 64,
        explanation={"lineage": ("obs-1",)},
    )
    summary = CitedSummary(
        summary_key="sum-1",
        provider_id="recorded-summary-v1",
        generated_at=AS_OF,
        segments=(SummarySegment("Recorded event", ("obs-1",), ("fixture://event-1",)),),
        policy_version="catalyst-summary-policy-v1",
        content_digest="e" * 64,
    )
    return SourceRunResult(
        run_key="run-key",
        source_id="recorded-company-news-v1",
        as_of=AS_OF,
        state=SourceState.AVAILABLE,
        observations=(observation,),
        quarantined=(quarantine,),
        decisions=(decision,),
        summaries=(summary,),
        reasons=(),
        result_digest="f" * 64,
    )
