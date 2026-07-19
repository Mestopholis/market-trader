from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_trader.scanner.models import (
    CandidateResult,
    ComponentScore,
    Direction,
    EligibilityResult,
    EligibilityStatus,
    EvidenceRef,
    FeatureSet,
    GateResult,
    PolicyVersions,
    RegimeResult,
    RegimeState,
    ScanCounts,
    ScannerInput,
    ScanResult,
    StrategyResult,
    StrategyStatus,
    SymbolInput,
)

AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)


def _reference(lineage_id: str = "lineage-1") -> EvidenceRef:
    return EvidenceRef(
        lineage_id=lineage_id,
        source="fixture",
        event_id=f"event-{lineage_id}",
        ingestion_key=f"ing-{lineage_id}",
        payload_digest="a" * 64,
        observed_at=AS_OF,
        ingested_at=AS_OF,
    )


def test_public_enums_contain_only_approved_values() -> None:
    assert tuple(Direction) == (Direction.BULLISH, Direction.BEARISH)
    assert tuple(EligibilityStatus) == (
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.INELIGIBLE,
        EligibilityStatus.BLOCKED,
    )
    assert tuple(RegimeState) == (
        RegimeState.BULLISH,
        RegimeState.BEARISH,
        RegimeState.NEUTRAL,
        RegimeState.MIXED,
        RegimeState.BLOCKED,
    )
    assert tuple(StrategyStatus) == (
        StrategyStatus.PASSED,
        StrategyStatus.FAILED,
        StrategyStatus.BLOCKED,
        StrategyStatus.NOT_APPLICABLE,
    )


def test_policy_versions_use_the_approved_identifiers() -> None:
    assert PolicyVersions() == PolicyVersions(
        universe="eligible-universe-v1",
        eligibility="eligibility-policy-v1",
        features="scanner-features-v1",
        regime="market-regime-v1",
        strategies="scanner-strategies-v1",
        scoring="candidate-scoring-v1",
        evidence="scanner-evidence-v1",
        fixture="scanner-fixture-v1",
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _reference().__class__(
            lineage_id="lineage",
            source="fixture",
            event_id="event",
            ingestion_key="ing",
            payload_digest="a" * 64,
            observed_at=datetime(2026, 7, 17, 10, 0),
            ingested_at=AS_OF,
        ),
        lambda: ScannerInput(
            as_of=datetime(2026, 7, 17, 10, 0),
            session_date=date(2026, 7, 17),
            versions=PolicyVersions(),
            symbols=(),
        ),
    ],
)
def test_naive_boundary_timestamps_are_rejected(factory: object) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        factory()  # type: ignore[operator]


def test_records_sort_and_deduplicate_reasons_lineage_and_named_children() -> None:
    gates = (
        GateResult(name="z_gate", passed=False, reasons=("z_reason", "a_reason")),
        GateResult(name="a_gate", passed=True),
    )
    components = (
        ComponentScore(
            family="z_family",
            pre_cap=Decimal("8"),
            cap=Decimal("5"),
            final=Decimal("5"),
        ),
        ComponentScore(
            family="a_family",
            pre_cap=Decimal("2"),
            cap=Decimal("10"),
            final=Decimal("2"),
        ),
    )
    strategy = StrategyResult(
        signal_key="signal-1",
        symbol="SPY",
        strategy_id="breakout",
        policy_version="scanner-strategies-v1",
        direction=Direction.BULLISH,
        status=StrategyStatus.FAILED,
        gates=gates,
        components=components,
        reasons=("z_reason", "a_reason", "z_reason"),
        lineage=("lineage-z", "lineage-a", "lineage-z"),
    )

    assert strategy.reasons == ("a_reason", "z_reason")
    assert strategy.lineage == ("lineage-a", "lineage-z")
    assert tuple(gate.name for gate in strategy.gates) == ("a_gate", "z_gate")
    assert tuple(component.family for component in strategy.components) == (
        "a_family",
        "z_family",
    )
    assert strategy.gates[1].reasons == ("a_reason", "z_reason")


def test_mapping_inputs_are_copied_and_immutable() -> None:
    attributes: dict[str, object] = {"role": "benchmark"}
    feature_values = {"adjusted_close": Decimal("625.25")}
    observed = {"daily_sessions": 200}
    symbol = SymbolInput(symbol="SPY", attributes=attributes)
    features = FeatureSet(symbol="SPY", values=feature_values)
    eligibility = EligibilityResult(
        symbol="SPY",
        status=EligibilityStatus.ELIGIBLE,
        policy_version="eligibility-policy-v1",
        observed=observed,
    )

    attributes["role"] = "changed"
    feature_values["adjusted_close"] = Decimal("1")
    observed["daily_sessions"] = 0

    assert symbol.attributes["role"] == "benchmark"
    assert features.values["adjusted_close"] == Decimal("625.25")
    assert eligibility.observed["daily_sessions"] == 200
    with pytest.raises(TypeError):
        symbol.attributes["role"] = "candidate"  # type: ignore[index]


def test_all_task_one_result_contracts_compose_into_a_scan_result() -> None:
    versions = PolicyVersions()
    regime = RegimeResult(
        state=RegimeState.BULLISH,
        signed_score=Decimal("55"),
        policy_version=versions.regime,
        components={"broad_trend": Decimal("30")},
    )
    eligibility = EligibilityResult(
        symbol="SPY",
        status=EligibilityStatus.ELIGIBLE,
        policy_version=versions.eligibility,
    )
    strategy = StrategyResult(
        signal_key="signal-1",
        symbol="SPY",
        strategy_id="bullish_breakout",
        policy_version=versions.strategies,
        direction=Direction.BULLISH,
        status=StrategyStatus.PASSED,
        score=Decimal("70"),
    )
    candidate = CandidateResult(
        candidate_key="candidate-1",
        signal_key="signal-1",
        symbol="SPY",
        strategy_id="bullish_breakout",
        direction=Direction.BULLISH,
        score=Decimal("70"),
    )
    result = ScanResult(
        run_key="run-1",
        as_of=AS_OF,
        session_date=date(2026, 7, 17),
        versions=versions,
        input_digest="b" * 64,
        regime=regime,
        eligibility=(eligibility,),
        strategies=(strategy,),
        candidates=(candidate,),
        counts=ScanCounts(eligible=1, signals=1, candidates=1),
        result_digest="c" * 64,
    )

    assert result.strategies[0].score == Decimal("70.000000")
    assert result.candidates[0].status == "qualified"
    assert result.counts == ScanCounts(eligible=1, signals=1, candidates=1)

