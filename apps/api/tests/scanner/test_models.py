from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from market_trader.market_data.models import (
    AdjustmentState,
    CandleInterval,
    NormalizedCandle,
    NormalizedProviderState,
    ObservationMetadata,
    ProviderOperationalState,
    QualityState,
)
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
from market_trader.scanner.serialization import stable_digest

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


def test_nested_mapping_inputs_cannot_mutate_records_or_digests() -> None:
    sectors = ["technology", "financials"]
    quality = {"states": sectors}
    attributes: dict[str, object] = {"quality": quality}
    symbol = SymbolInput(symbol="SPY", attributes=attributes)
    original_digest = stable_digest(symbol)

    sectors.append("energy")
    quality["states"] = ["changed"]
    attributes["quality"] = {"states": ["replaced"]}

    frozen_quality = cast(Mapping[str, object], symbol.attributes["quality"])
    assert frozen_quality["states"] == ("technology", "financials")
    assert stable_digest(symbol) == original_digest
    with pytest.raises(TypeError):
        frozen_quality["states"] = ()  # type: ignore[index]


def test_tied_evidence_and_market_observations_have_total_order() -> None:
    metadata = ObservationMetadata(
        source="fixture",
        event_id="tied-event",
        observed_at=AS_OF,
        ingested_at=AS_OF,
        session_date=date(2026, 7, 17),
        normalized_schema_version=1,
        configuration_version="market-data-v1",
        correlation_id="correlation-1",
        quality_state=QualityState.VALID,
        quality_reasons=(),
    )
    candle_a = NormalizedCandle(
        symbol="SPY",
        interval=CandleInterval.ONE_MINUTE,
        start=AS_OF - timedelta(minutes=1),
        end=AS_OF,
        open=Decimal("625"),
        high=Decimal("626"),
        low=Decimal("624"),
        close=Decimal("625"),
        volume=100,
        vwap=Decimal("625"),
        trade_count=10,
        adjustment=AdjustmentState.ADJUSTED,
        metadata=metadata,
    )
    candle_b = replace(candle_a, close=Decimal("625.5"))
    provider_a = NormalizedProviderState(
        provider="fixture-a",
        state=ProviderOperationalState.AVAILABLE,
        metadata=metadata,
    )
    provider_b = replace(provider_a, provider="fixture-b")
    evidence_a = _reference("tied-lineage")
    evidence_b = replace(evidence_a, observed_at=AS_OF - timedelta(seconds=1))

    left = SymbolInput(
        symbol="SPY",
        intraday_candles=(candle_a, candle_b),
        provider_states=(provider_a, provider_b),
        evidence=(evidence_a, evidence_b),
    )
    right = SymbolInput(
        symbol="SPY",
        intraday_candles=(candle_b, candle_a),
        provider_states=(provider_b, provider_a),
        evidence=(evidence_b, evidence_a),
    )

    assert stable_digest(left) == stable_digest(right)


def test_tied_symbols_gates_and_components_have_total_order() -> None:
    symbol_a = SymbolInput(symbol="SPY", attributes={"role": "a"})
    symbol_b = SymbolInput(symbol="SPY", attributes={"role": "b"})
    scanner_left = ScannerInput(
        as_of=AS_OF,
        session_date=date(2026, 7, 17),
        versions=PolicyVersions(),
        symbols=(symbol_a, symbol_b),
    )
    scanner_right = replace(scanner_left, symbols=(symbol_b, symbol_a))
    gate_a = GateResult(name="trigger", passed=True, observed={"value": "a"})
    gate_b = GateResult(name="trigger", passed=False, observed={"value": "b"})
    component_a = ComponentScore(
        family="price_structure",
        pre_cap=Decimal("10"),
        cap=Decimal("30"),
        final=Decimal("10"),
    )
    component_b = replace(component_a, final=Decimal("20"))
    strategy_left = StrategyResult(
        signal_key="signal",
        symbol="SPY",
        strategy_id="breakout",
        policy_version="scanner-strategies-v1",
        direction=Direction.BULLISH,
        status=StrategyStatus.FAILED,
        gates=(gate_a, gate_b),
        components=(component_a, component_b),
    )
    strategy_right = replace(
        strategy_left,
        gates=(gate_b, gate_a),
        components=(component_b, component_a),
    )

    assert stable_digest(scanner_left) == stable_digest(scanner_right)
    assert stable_digest(strategy_left) == stable_digest(strategy_right)


def test_tied_scan_results_have_total_order() -> None:
    versions = PolicyVersions()
    regime = RegimeResult(
        state=RegimeState.NEUTRAL,
        signed_score=Decimal("0"),
        policy_version=versions.regime,
    )
    strategy_a = StrategyResult(
        signal_key="signal-a",
        symbol="SPY",
        strategy_id="breakout",
        policy_version=versions.strategies,
        direction=Direction.BULLISH,
        status=StrategyStatus.PASSED,
    )
    strategy_b = replace(strategy_a, signal_key="signal-b")
    candidate_a = CandidateResult(
        candidate_key="candidate-a",
        signal_key="signal-a",
        symbol="SPY",
        strategy_id="breakout",
        direction=Direction.BULLISH,
        score=Decimal("70"),
    )
    candidate_b = replace(
        candidate_a,
        candidate_key="candidate-b",
        signal_key="signal-b",
    )
    left = ScanResult(
        run_key="run",
        as_of=AS_OF,
        session_date=date(2026, 7, 17),
        versions=versions,
        input_digest="a" * 64,
        regime=regime,
        eligibility=(),
        strategies=(strategy_a, strategy_b),
        candidates=(candidate_a, candidate_b),
        counts=ScanCounts(signals=2, candidates=2),
        result_digest="b" * 64,
    )
    right = replace(
        left,
        strategies=(strategy_b, strategy_a),
        candidates=(candidate_b, candidate_a),
    )

    assert stable_digest(left) == stable_digest(right)


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
