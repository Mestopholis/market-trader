from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from market_trader.db.models import (
    CandidateORM,
    MarketDataSnapshotORM,
    OptionsAnalysisRunORM,
    RiskDecisionORM,
    RiskLockORM,
    ScannerRunORM,
    SignalORM,
    SymbolORM,
)
from market_trader.paper.eligibility import assemble_approval_cards
from market_trader.paper.models import ApprovalCardState, PaperAction

from ..db_helpers import migrated_engine

AS_OF = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)


def test_generates_cards_for_approved_and_warning_risk_decisions(tmp_path: Any) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        _candidate(session, key="candidate-a", symbol="MSFT", direction="long")
        _candidate(session, key="candidate-b", symbol="AAPL", direction="short")
        _risk_decision(session, key="risk-a", candidate_key="candidate-a", status="approved")
        _risk_decision(
            session,
            key="risk-b",
            candidate_key="candidate-b",
            status="warning",
            warnings=["near portfolio concentration limit"],
        )
        session.commit()

        cards = assemble_approval_cards(session, as_of=AS_OF)

    engine.dispose()

    assert [card.risk_decision_key for card in cards] == ["risk-a", "risk-b"]
    assert cards[0].state is ApprovalCardState.READY
    assert cards[0].candidate_key == "candidate-a"
    assert cards[0].symbol == "MSFT"
    assert cards[0].direction == "long"
    assert cards[0].proposal_kind == "single"
    assert cards[0].quantity == 2
    assert cards[0].limit_price == Decimal("1.25")
    assert cards[0].maximum_loss == Decimal("250.00")
    assert cards[0].risk_input_digest == "risk-input-candidate-a"
    assert cards[0].risk_result_digest == "risk-result-risk-a"
    assert cards[0].source_keys == (
        "candidate:candidate-a",
        "risk_decision:risk-a",
        "signal:signal-candidate-a",
    )
    assert cards[0].allowed_actions == (
        PaperAction.APPROVE,
        PaperAction.MODIFY,
        PaperAction.REJECT,
    )
    assert cards[0].expires_at == datetime(2026, 7, 20, 15, 5, tzinfo=UTC)
    assert cards[0].as_of == AS_OF
    assert cards[1].warnings == ("near portfolio concentration limit",)


def test_omits_cards_without_eligible_risk_status(tmp_path: Any) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        _candidate(session, key="candidate-a")
        _risk_decision(session, key="risk-a", candidate_key="candidate-a", status="blocked")
        session.commit()

        cards = assemble_approval_cards(session, as_of=AS_OF)

    engine.dispose()

    assert cards == ()


def test_omits_cards_without_positive_quantity(tmp_path: Any) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        _candidate(session, key="candidate-a")
        _risk_decision(session, key="risk-a", candidate_key="candidate-a", quantity=0)
        session.commit()

        cards = assemble_approval_cards(session, as_of=AS_OF)

    engine.dispose()

    assert cards == ()


def test_omits_cards_without_candidate_lineage(tmp_path: Any) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        _risk_decision(session, key="risk-a", candidate_key="missing-candidate")
        session.commit()

        cards = assemble_approval_cards(session, as_of=AS_OF)

    engine.dispose()

    assert cards == ()


def test_omits_cards_when_candidate_digest_is_stale(tmp_path: Any) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        _candidate(session, key="candidate-a", input_digest="candidate-input-current")
        _risk_decision(
            session,
            key="risk-a",
            candidate_key="candidate-a",
            candidate_input_digest="candidate-input-old",
        )
        session.commit()

        cards = assemble_approval_cards(session, as_of=AS_OF)

    engine.dispose()

    assert cards == ()


def test_debit_spread_cards_require_persisted_options_analysis(tmp_path: Any) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        candidate = _candidate(session, key="candidate-a")
        _risk_decision(
            session,
            key="risk-a",
            candidate_key="candidate-a",
            proposal_kind="debit_spread",
        )
        session.commit()

        assert assemble_approval_cards(session, as_of=AS_OF) == ()

        _options_analysis(session, candidate=candidate)
        session.commit()

        cards = assemble_approval_cards(session, as_of=AS_OF)

    engine.dispose()

    assert [card.risk_decision_key for card in cards] == ["risk-a"]
    assert cards[0].source_keys == (
        "candidate:candidate-a",
        "options_analysis:options-run-candidate-a",
        "risk_decision:risk-a",
        "signal:signal-candidate-a",
    )


def test_active_required_risk_lock_blocks_cards(tmp_path: Any) -> None:
    engine = migrated_engine(tmp_path)
    with Session(engine) as session:
        _candidate(session, key="candidate-a")
        _risk_decision(session, key="risk-a", candidate_key="candidate-a")
        session.add(
            RiskLockORM(
                id="lock-a",
                lock_type="daily_loss",
                status="active",
                reason="daily loss limit reached",
                source_event_id=None,
                activated_at=AS_OF,
                cleared_at=None,
                clearing_event_id=None,
                payload={},
                payload_schema_version=1,
                correlation_id="corr-lock-a",
            )
        )
        session.commit()

        cards = assemble_approval_cards(session, as_of=AS_OF)

    engine.dispose()

    assert cards == ()


def _candidate(
    session: Session,
    *,
    key: str,
    symbol: str = "MSFT",
    direction: str = "long",
    input_digest: str = "candidate-input-current",
) -> CandidateORM:
    symbol_record = SymbolORM(
        id=f"symbol-{key}",
        display_symbol=symbol,
        instrument_type="equity",
        exchange="NASDAQ",
        is_active=True,
        first_observed_at=AS_OF,
        last_observed_at=AS_OF,
        metadata_payload={},
        metadata_schema_version=1,
        correlation_id=f"corr-{key}",
    )
    snapshot = MarketDataSnapshotORM(
        id=f"snapshot-{key}",
        ingestion_key=f"snapshot-ingestion-{key}",
        payload_digest=f"snapshot-digest-{key}",
        source="fixture",
        data_kind="quote",
        symbol_id=symbol_record.id,
        instrument_id=None,
        observed_at=AS_OF,
        ingested_at=AS_OF,
        session_date=date(2026, 7, 20),
        quality_state="ok",
        configuration_version_id=None,
        payload={},
        payload_schema_version=1,
        correlation_id=f"corr-{key}",
    )
    scanner_run = ScannerRunORM(
        id=f"scanner-{key}",
        run_key=f"scanner-run-{key}",
        as_of=AS_OF,
        session_date=date(2026, 7, 20),
        input_digest=f"scanner-input-{key}",
        universe_version="test",
        universe_content_hash=f"universe-hash-{key}",
        policy_versions={"scanner": "v1"},
        regime_state="risk_on",
        regime_score=Decimal("0.500000"),
        regime_explanation={},
        result_counts={},
        result_digest=f"scanner-result-{key}",
        status="completed",
        correlation_id=f"corr-{key}",
        created_at=AS_OF,
    )
    signal = SignalORM(
        id=f"signal-{key}",
        signal_key=f"signal-{key}",
        scanner_run_id=scanner_run.id,
        strategy_id="momentum",
        strategy_version="v1",
        symbol_id=symbol_record.id,
        instrument_id=None,
        direction=direction,
        score=Decimal("0.750000"),
        status="eligible",
        input_snapshot_id=snapshot.id,
        input_digest=f"signal-input-{key}",
        reason_codes=[],
        gate_payload=[],
        component_score_payload=[],
        scoring_policy_version="signal-v1",
        explanation_payload={},
        explanation_schema_version=1,
        correlation_id=f"corr-{key}",
        created_at=AS_OF,
    )
    candidate = CandidateORM(
        id=f"candidate-id-{key}",
        candidate_key=key,
        scanner_run_id=scanner_run.id,
        strategy_id="momentum",
        signal_id=signal.id,
        symbol_id=symbol_record.id,
        instrument_id=None,
        direction=direction,
        status="ready",
        score=Decimal("0.700000"),
        input_digest=input_digest,
        scoring_policy_version="candidate-v1",
        explanation_payload={},
        explanation_schema_version=1,
        correlation_id=f"corr-{key}",
        created_at=AS_OF,
    )
    session.add(symbol_record)
    session.flush()
    session.add_all([snapshot, scanner_run])
    session.flush()
    session.add(signal)
    session.flush()
    session.add(candidate)
    session.flush()
    return candidate


def _risk_decision(
    session: Session,
    *,
    key: str,
    candidate_key: str,
    status: str = "approved",
    proposal_kind: str = "single",
    quantity: int = 2,
    candidate_input_digest: str = "candidate-input-current",
    warnings: list[str] | None = None,
) -> RiskDecisionORM:
    decision = RiskDecisionORM(
        id=f"risk-id-{key}",
        decision_key=key,
        status=status,
        proposal_kind=proposal_kind,
        policy_version="risk-v1",
        policy_hash=f"risk-policy-hash-{key}",
        input_digest=f"risk-input-{candidate_key}",
        result_digest=f"risk-result-{key}",
        as_of=AS_OF,
        reason_summary=warnings or [],
        sizing_payload={
            "quantity": quantity,
            "maximum_loss": "250.00",
        },
        decision_payload={
            "candidate_key": candidate_key,
            "candidate_input_digest": candidate_input_digest,
            "limit_price": "1.25",
            "source_keys": [f"risk_decision:{key}"],
        },
        correlation_id=f"corr-{key}",
        created_at=AS_OF,
    )
    session.add(decision)
    return decision


def _options_analysis(session: Session, *, candidate: CandidateORM) -> OptionsAnalysisRunORM:
    run = OptionsAnalysisRunORM(
        id=f"options-id-{candidate.candidate_key}",
        run_key=f"options-run-{candidate.candidate_key}",
        scanner_run_id=str(candidate.scanner_run_id),
        candidate_id=candidate.id,
        symbol_id=candidate.symbol_id,
        input_digest=f"options-input-{candidate.candidate_key}",
        result_digest=f"options-result-{candidate.candidate_key}",
        policy_version="options-v1",
        policy_hash=f"options-policy-hash-{candidate.candidate_key}",
        as_of=AS_OF,
        result_counts={},
        reason_summary={},
        created_at=AS_OF,
    )
    session.add(run)
    return run
