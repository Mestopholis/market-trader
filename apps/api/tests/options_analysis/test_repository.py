from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from market_trader.db.base import Base
from market_trader.db.models import (
    CandidateORM,
    JournalEventORM,
    OptionContractEvaluationORM,
    OptionsAnalysisRunORM,
    OptionSpreadCandidateORM,
    OptionSpreadWarningORM,
    ScannerRunORM,
    SymbolORM,
)
from market_trader.options_analysis.engine import OptionsAnalysisResult, RankedSpread
from market_trader.options_analysis.models import (
    ContractEvaluation,
    EvaluationState,
    SpreadCandidate,
    SpreadStrategy,
)
from market_trader.options_analysis.warnings import SpreadWarning
from market_trader.repositories.options_analysis import (
    OptionsAnalysisPersistenceConflict,
    OptionsAnalysisPersistenceError,
    OptionsAnalysisRepository,
)

AS_OF = datetime(2026, 8, 14, 14, 30, tzinfo=UTC)


@pytest.fixture
def session() -> Generator[Session]:
    sqlite_engine = create_engine("sqlite://")
    Base.metadata.create_all(sqlite_engine)
    try:
        with Session(sqlite_engine) as value:
            _seed_lineage(value)
            yield value
    finally:
        sqlite_engine.dispose()


def _seed_lineage(session: Session) -> None:
    session.add(
        SymbolORM(
            id="sym-1",
            display_symbol="AAPL",
            instrument_type="equity",
            exchange="XNYS",
            is_active=True,
            first_observed_at=AS_OF,
            last_observed_at=AS_OF,
            metadata_payload={},
            metadata_schema_version=1,
            correlation_id="seed",
        )
    )
    session.add(
        ScannerRunORM(
            id="scanner-1",
            run_key="scanner-run-1",
            as_of=AS_OF,
            session_date=date(2026, 8, 14),
            input_digest="1" * 64,
            universe_version="universe-v1",
            universe_content_hash="2" * 64,
            policy_versions={},
            regime_state="risk_on",
            regime_score=Decimal("0.500000"),
            regime_explanation={},
            result_counts={},
            result_digest="3" * 64,
            status="completed",
            correlation_id="seed",
            created_at=AS_OF,
        )
    )
    session.add(
        CandidateORM(
            id="candidate-1",
            candidate_key="candidate-1",
            scanner_run_id="scanner-1",
            strategy_id="breakout",
            signal_id="signal-1",
            symbol_id="sym-1",
            instrument_id=None,
            direction="bullish",
            status="qualified",
            score=Decimal("0.800000"),
            input_digest="4" * 64,
            scoring_policy_version="scoring-v1",
            explanation_payload={},
            explanation_schema_version=1,
            correlation_id="seed",
            created_at=AS_OF,
        )
    )
    session.flush()


def _spread() -> SpreadCandidate:
    return SpreadCandidate(
        strategy=SpreadStrategy.BULL_CALL,
        long_contract_id="AAPL-20260918-C-200",
        short_contract_id="AAPL-20260918-C-205",
        expiration=date(2026, 9, 18),
        debit=Decimal("1.25"),
        maximum_loss=Decimal("125.00"),
        maximum_gain=Decimal("375.00"),
        break_even=Decimal("201.25"),
        net_delta=Decimal("0.20"),
        net_gamma=Decimal("0.01"),
        net_theta=Decimal("-0.03"),
        net_vega=Decimal("0.08"),
        liquidity_open_interest=100,
        liquidity_volume=50,
    )


def _result(*, result_digest: str = "b" * 64) -> OptionsAnalysisResult:
    return OptionsAnalysisResult(
        selectable=(
            RankedSpread(
                candidate=_spread(),
                blocked=False,
                warnings=(SpreadWarning("pin_risk", "warning"),),
            ),
        ),
        blocked=(),
        evaluations=(
            ContractEvaluation(
                contract_id="AAPL-20260918-C-200",
                state=EvaluationState.ACCEPTED,
                reasons=(),
            ),
        ),
        run_key="options-run-1",
        scanner_run_key="scanner-run-1",
        candidate_key="candidate-1",
        symbol="AAPL",
        input_digest="a" * 64,
        result_digest=result_digest,
        policy_version="options-analysis-policy-v1",
        policy_hash="c" * 64,
        as_of=AS_OF,
    )


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_persist_records_run_children_and_audit_events_without_committing(session: Session) -> None:
    persisted = OptionsAnalysisRepository(session).persist(_result())

    assert persisted.run_key == "options-run-1"
    assert persisted.correlation_id
    assert _count(session, OptionsAnalysisRunORM) == 1
    assert _count(session, OptionContractEvaluationORM) == 1
    assert _count(session, OptionSpreadCandidateORM) == 1
    assert _count(session, OptionSpreadWarningORM) == 1
    event_types = session.scalars(
        select(JournalEventORM.event_type).order_by(JournalEventORM.event_type)
    ).all()
    assert event_types == [
        "option_contract_evaluation.recorded",
        "option_spread_candidate.recorded",
        "option_spread_warning.recorded",
        "options_analysis_run.recorded",
    ]
    session.rollback()
    assert _count(session, OptionsAnalysisRunORM) == 0


def test_exact_rerun_returns_existing_record_without_duplicate_children_or_audit(
    session: Session,
) -> None:
    repository = OptionsAnalysisRepository(session)
    first = repository.persist(_result())
    second = repository.persist(_result())

    assert first.id == second.id
    assert _count(session, OptionsAnalysisRunORM) == 1
    assert _count(session, OptionSpreadCandidateORM) == 1
    assert _count(session, JournalEventORM) == 4


def test_changed_digest_for_existing_run_key_is_a_conflict(session: Session) -> None:
    repository = OptionsAnalysisRepository(session)
    repository.persist(_result())

    with pytest.raises(OptionsAnalysisPersistenceConflict):
        repository.persist(_result(result_digest="d" * 64))


def test_missing_candidate_lineage_is_rejected_before_records_are_written(session: Session) -> None:
    result = OptionsAnalysisResult(
        **{**_result().__dict__, "candidate_key": "missing-candidate"}
    )

    with pytest.raises(OptionsAnalysisPersistenceError, match="missing candidate"):
        OptionsAnalysisRepository(session).persist(result)

    assert _count(session, OptionsAnalysisRunORM) == 0


def test_child_failure_rolls_back_the_entire_persist_attempt(session: Session) -> None:
    duplicate_warnings = (
        RankedSpread(
            candidate=_spread(),
            blocked=False,
            warnings=(
                SpreadWarning("pin_risk", "warning"),
                SpreadWarning("pin_risk", "warning"),
            ),
        ),
    )
    result = OptionsAnalysisResult(**{**_result().__dict__, "selectable": duplicate_warnings})

    with pytest.raises(OptionsAnalysisPersistenceError, match="duplicate warning"):
        OptionsAnalysisRepository(session).persist(result)

    assert _count(session, OptionsAnalysisRunORM) == 0
    assert _count(session, OptionSpreadCandidateORM) == 0
    assert _count(session, OptionSpreadWarningORM) == 0
    assert _count(session, JournalEventORM) == 0
