from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from market_trader.config import get_settings
from market_trader.dashboard.models import DataState
from market_trader.dashboard.read_models import DashboardReadModel
from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.db.models import (
    CandidateORM,
    JournalEventORM,
    MarketDataSnapshotORM,
    RiskCheckORM,
    RiskDecisionORM,
    ScannerRunORM,
    SignalORM,
    SymbolORM,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


@pytest.fixture()
def database_url(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'dashboard.db'}"
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", url)
    get_settings.cache_clear()
    upgrade_to_head(url)
    return url


def test_candidate_list_reads_persisted_candidates(database_url: str) -> None:
    _seed_candidate(database_url)

    response = DashboardReadModel().candidates(limit=10, cursor=None)

    assert response.data_state is DataState.READY
    assert len(response.candidates) == 1
    candidate = response.candidates[0]
    assert candidate.candidate_key == "candidate:aapl"
    assert candidate.symbol == "AAPL"
    assert candidate.strategy == "bullish_breakout"
    assert candidate.score == "87.500000"


def test_journal_and_analytics_read_persisted_rows(database_url: str) -> None:
    _seed_candidate(database_url)

    journal = DashboardReadModel().journal(
        limit=10,
        cursor=None,
        event_type=None,
        correlation_id=None,
    )
    analytics = DashboardReadModel().analytics()

    assert journal.data_state is DataState.READY
    assert [event.event_type for event in journal.events] == ["scanner_run.completed"]
    assert analytics.data_state is DataState.READY
    assert analytics.candidate_counts == {"qualified": 1}
    assert analytics.strategy_mix == {"bullish_breakout": 1}


def test_risk_reads_latest_persisted_decision(database_url: str) -> None:
    _seed_candidate(database_url)
    _seed_risk(database_url)

    risk = DashboardReadModel().risk()

    assert risk.data_state is DataState.READY
    assert risk.latest_decision_key == "risk:decision:aapl"
    assert risk.status == "approved"
    assert [check.code for check in risk.checks] == ["position_size"]


def _seed_candidate(database_url: str) -> None:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session, session.begin():
            session.add(
                SymbolORM(
                    id="symbol-aapl",
                    display_symbol="AAPL",
                    instrument_type="equity",
                    exchange="XNAS",
                    is_active=True,
                    first_observed_at=AS_OF,
                    last_observed_at=AS_OF,
                    metadata_payload={"schema_version": 1},
                    metadata_schema_version=1,
                    correlation_id="corr-seed",
                )
            )
            session.flush()
            session.add(
                MarketDataSnapshotORM(
                    id="snapshot-aapl",
                    ingestion_key="fixture:aapl",
                    payload_digest="digest-snapshot",
                    source="fixture",
                    data_kind="quote",
                    symbol_id="symbol-aapl",
                    instrument_id=None,
                    observed_at=AS_OF,
                    ingested_at=AS_OF,
                    session_date=AS_OF.date(),
                    quality_state="accepted",
                    configuration_version_id=None,
                    payload={"bid": "100.00", "ask": "100.10"},
                    payload_schema_version=1,
                    correlation_id="corr-seed",
                )
            )
            session.flush()
            session.add(
                ScannerRunORM(
                    id="scanner-run-a",
                    run_key="scanner:run:a",
                    as_of=AS_OF,
                    session_date=AS_OF.date(),
                    input_digest="digest-input",
                    universe_version="eligible-universe-v1",
                    universe_content_hash="hash",
                    policy_versions={"scoring": "candidate-scoring-v1"},
                    regime_state="bullish",
                    regime_score=Decimal("72.000000"),
                    regime_explanation={"summary": "Synthetic regime"},
                    result_counts={"candidates": 1},
                    result_digest="digest-result",
                    status="completed",
                    correlation_id="corr-scan",
                    created_at=AS_OF,
                )
            )
            session.flush()
            session.add(
                SignalORM(
                    id="signal-aapl",
                    signal_key="signal:aapl",
                    scanner_run_id="scanner-run-a",
                    strategy_id="bullish_breakout",
                    strategy_version="scanner-strategies-v1",
                    symbol_id="symbol-aapl",
                    instrument_id=None,
                    direction="bullish",
                    score=Decimal("87.500000"),
                    status="qualified",
                    input_snapshot_id="snapshot-aapl",
                    input_digest="digest-signal",
                    reason_codes=["score.momentum"],
                    gate_payload=[],
                    component_score_payload=[],
                    scoring_policy_version="candidate-scoring-v1",
                    explanation_payload={"summary": "Synthetic candidate"},
                    explanation_schema_version=1,
                    correlation_id="corr-scan",
                    created_at=AS_OF,
                )
            )
            session.flush()
            session.add(
                CandidateORM(
                    id="candidate-aapl",
                    candidate_key="candidate:aapl",
                    scanner_run_id="scanner-run-a",
                    strategy_id="bullish_breakout",
                    signal_id="signal-aapl",
                    symbol_id="symbol-aapl",
                    instrument_id=None,
                    direction="bullish",
                    status="qualified",
                    score=Decimal("87.500000"),
                    input_digest="digest-candidate",
                    scoring_policy_version="candidate-scoring-v1",
                    explanation_payload={"reason_codes": ["score.momentum"]},
                    explanation_schema_version=1,
                    correlation_id="corr-scan",
                    created_at=AS_OF,
                )
            )
            session.add(
                JournalEventORM(
                    id="journal-a",
                    correlation_id="corr-scan",
                    event_type="scanner_run.completed",
                    actor_type="system",
                    occurred_at=AS_OF,
                    recorded_at=AS_OF,
                    subject_type="scanner_run",
                    subject_id="scanner-run-a",
                    causation_event_id=None,
                    payload={"qualified": 1},
                    schema_version=1,
                )
            )
    finally:
        engine.dispose()


def _seed_risk(database_url: str) -> None:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session, session.begin():
            session.add(
                RiskDecisionORM(
                    id="risk-aapl",
                    decision_key="risk:decision:aapl",
                    status="approved",
                    proposal_kind="shares",
                    policy_version="risk-policy-v1",
                    policy_hash="hash-risk",
                    input_digest="digest-candidate",
                    result_digest="digest-risk",
                    as_of=AS_OF,
                    reason_summary=["position_size"],
                    sizing_payload={
                        "quantity": 10,
                        "maximum_loss": "150.00",
                        "limit_price": "100.25",
                    },
                    decision_payload={
                        "candidate_key": "candidate:aapl",
                        "candidate_input_digest": "digest-candidate",
                        "limit_price": "100.25",
                    },
                    correlation_id="corr-risk",
                    created_at=AS_OF,
                )
            )
            session.flush()
            session.add(
                RiskCheckORM(
                    id="risk-check-aapl",
                    check_key="risk:check:aapl",
                    decision_id="risk-aapl",
                    code="position_size",
                    severity="info",
                    state="passed",
                    facts={"quantity": 10},
                    source_keys=["candidate:aapl"],
                    created_at=AS_OF,
                )
            )
    finally:
        engine.dispose()
