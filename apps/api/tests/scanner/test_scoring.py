from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.features import FeatureResult, FiveMinuteBar
from market_trader.scanner.models import (
    Direction,
    EligibilityResult,
    EligibilityStatus,
    GateResult,
    RegimeResult,
    RegimeState,
    StrategyResult,
    StrategyStatus,
)
from market_trader.scanner.scoring import CandidateScorer, CandidateSelector

CONFIGURATION_PATH = Path(__file__).parents[2] / "config" / "scanner"
POLICY = load_scanner_configuration(CONFIGURATION_PATH).scoring
AS_OF = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)


def test_candidate_scorer_exposes_policy_version() -> None:
    assert CandidateScorer.version == "candidate-scoring-v1"
    assert CandidateScorer(POLICY).version == POLICY.version


def _gate(name: str, passed: bool | None = True) -> GateResult:
    return GateResult(name=name, passed=passed)


def _strategy(
    *,
    strategy_id: str = "bullish_breakout",
    direction: Direction = Direction.BULLISH,
    status: StrategyStatus = StrategyStatus.PASSED,
    gates: tuple[GateResult, ...] | None = None,
    lineage: tuple[str, ...] = ("regime-lineage",),
) -> StrategyResult:
    return StrategyResult(
        signal_key=f"run:AAPL:{strategy_id}:scanner-strategies-v1",
        symbol="AAPL",
        strategy_id=strategy_id,
        policy_version="scanner-strategies-v1",
        direction=direction,
        status=status,
        gates=gates
        or (
            _gate("established_trend"),
            _gate("price_trigger"),
            _gate("regime_compatibility"),
            _gate("relative_volume"),
            _gate("vwap_position"),
        ),
        lineage=lineage,
        input_digest="a" * 64,
    )


def _features(direction: Direction = Direction.BULLISH) -> FeatureResult:
    if direction is Direction.BULLISH:
        close, trigger, vwap, relative_strength = "111", "110", "110", "85"
        prior_high, prior_low = trigger, None
    else:
        close, trigger, vwap, relative_strength = "89", "90", "90", "15"
        prior_high, prior_low = None, trigger
    return FeatureResult(
        symbol="AAPL",
        adjusted_close=Decimal(close),
        prior_20_high=Decimal(prior_high) if prior_high else None,
        prior_20_low=Decimal(prior_low) if prior_low else None,
        median_dollar_volume_20=Decimal("100000000"),
        session_open=Decimal("100"),
        session_close=Decimal(close),
        session_vwap=Decimal(vwap),
        relative_volume_20=Decimal("2.00"),
        relative_strength_percentile_20=Decimal(relative_strength),
    )


def _regime(
    state: RegimeState = RegimeState.BULLISH,
    score: str = "35",
    lineage: tuple[str, ...] = ("regime-lineage",),
) -> RegimeResult:
    return RegimeResult(
        state=state,
        signed_score=Decimal(score),
        policy_version="market-regime-v1",
        lineage=lineage,
    )


def _components(result: StrategyResult) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    return {
        component.family: (component.pre_cap, component.cap, component.final)
        for component in result.components
    }


def test_technical_maximum_scores_each_family_without_catalyst() -> None:
    result = CandidateScorer(POLICY).score(
        _strategy(),
        _features(),
        _regime(),
    )

    assert _components(result) == {
        "catalyst": (Decimal("0.000000"), Decimal("10.000000"), Decimal("0.000000")),
        "market_direction": (
            Decimal("25.000000"),
            Decimal("25.000000"),
            Decimal("25.000000"),
        ),
        "participation_liquidity": (
            Decimal("20.000000"),
            Decimal("20.000000"),
            Decimal("20.000000"),
        ),
        "price_structure": (
            Decimal("30.000000"),
            Decimal("30.000000"),
            Decimal("30.000000"),
        ),
        "relative_performance": (
            Decimal("15.000000"),
            Decimal("15.000000"),
            Decimal("15.000000"),
        ),
    }
    assert result.score == Decimal("90.000000")
    assert all(
        isinstance(value, Decimal) for values in _components(result).values() for value in values
    )


@pytest.mark.parametrize(
    ("state", "score", "strategy_id", "expected"),
    [
        (RegimeState.BULLISH, "35", "bullish_pullback", "25"),
        (RegimeState.NEUTRAL, "0", "bullish_pullback", "20"),
        (RegimeState.MIXED, "20", "bullish_pullback", "20"),
        (RegimeState.BEARISH, "-35", "bullish_pullback", "15"),
        (RegimeState.BLOCKED, "0", "bullish_pullback", "15"),
        (RegimeState.NEUTRAL, "0", "bullish_breakout", "15"),
    ],
)
def test_market_direction_contributions(
    state: RegimeState, score: str, strategy_id: str, expected: str
) -> None:
    strategy = _strategy(
        strategy_id=strategy_id,
        gates=(_gate("established_trend"), _gate("regime_compatibility")),
    )

    result = CandidateScorer(POLICY).score(
        strategy,
        _features(),
        _regime(state, score),
    )

    component = next(item for item in result.components if item.family == "market_direction")
    assert component.final == Decimal(expected).quantize(POLICY.score_quantum)
    assert component.lineage == ("regime-lineage",)


def test_reversal_and_news_price_structure_use_their_declared_triggers() -> None:
    previous = FiveMinuteBar(
        start=AS_OF,
        end=AS_OF,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("98"),
        close=Decimal("99"),
        volume=1,
    )
    latest = replace(
        previous,
        open=Decimal("100"),
        high=Decimal("101"),
        close=Decimal("100.25"),
    )
    reversal_features = replace(
        _features(),
        session_close=Decimal("100.25"),
        session_vwap=Decimal("100"),
        five_minute_bars=(previous, latest),
    )
    reversal = _strategy(
        strategy_id="bullish_pullback",
        gates=(
            _gate("established_trend"),
            _gate("regime_compatibility"),
            _gate("reversal_confirmation"),
        ),
    )
    news = _strategy(
        strategy_id="news_continuation",
        gates=(
            _gate("material_catalyst"),
            _gate("regime_compatibility"),
            _gate("relative_volume"),
            _gate("session_open_hold"),
            _gate("vwap_position"),
        ),
        lineage=("catalyst-lineage", "regime-lineage"),
    )

    scored_reversal = CandidateScorer(POLICY).score(reversal, reversal_features, _regime())
    scored_news = CandidateScorer(POLICY).score(news, _features(), _regime())

    assert _components(scored_reversal)["price_structure"][2] == Decimal("30.000000")
    assert _components(scored_news)["price_structure"][2] == Decimal("30.000000")
    assert _components(scored_news)["catalyst"][2] == Decimal("10.000000")


def test_participation_and_relative_performance_boundaries() -> None:
    scorer = CandidateScorer(POLICY)
    standard = scorer.score(
        _strategy(),
        replace(
            _features(),
            relative_volume_20=Decimal("1.50"),
            relative_strength_percentile_20=Decimal("70"),
        ),
        _regime(),
    )
    below = scorer.score(
        _strategy(),
        replace(
            _features(),
            relative_volume_20=Decimal("1.499999"),
            relative_strength_percentile_20=Decimal("69.999999"),
        ),
        _regime(),
    )

    assert _components(standard)["participation_liquidity"][2] == Decimal("15.000000")
    assert _components(standard)["relative_performance"][2] == Decimal("10.000000")
    assert _components(below)["participation_liquidity"][2] == Decimal("5.000000")
    assert _components(below)["relative_performance"][2] == Decimal("0.000000")


def test_bearish_relative_performance_uses_inverse_boundaries() -> None:
    strategy = _strategy(
        strategy_id="bearish_breakdown",
        direction=Direction.BEARISH,
    )
    exceptional = CandidateScorer(POLICY).score(
        strategy,
        _features(Direction.BEARISH),
        _regime(RegimeState.BEARISH, "-35"),
    )

    assert _components(exceptional)["relative_performance"][2] == Decimal("15.000000")


def test_duplicate_lineage_is_counted_once_and_family_caps_are_independent() -> None:
    news = _strategy(
        strategy_id="news_continuation",
        gates=(_gate("material_catalyst"), _gate("session_open_hold")),
        lineage=("catalyst-a", "catalyst-a", "regime-lineage"),
    )

    result = CandidateScorer(POLICY).score(news, _features(), _regime())
    catalyst = next(item for item in result.components if item.family == "catalyst")

    assert catalyst.pre_cap == Decimal("10.000000")
    assert catalyst.final == Decimal("10.000000")
    assert catalyst.lineage == ("catalyst-a",)
    assert _components(result)["price_structure"][2] <= Decimal("30.000000")


def test_total_is_clamped_to_one_hundred_with_six_decimal_arithmetic() -> None:
    inflated = replace(
        POLICY,
        family_caps=MappingProxyType({family: Decimal("200") for family in POLICY.family_caps}),
        component_points=MappingProxyType(
            {name: Decimal("100.0000004") for name in POLICY.component_points}
        ),
    )

    result = CandidateScorer(inflated).score(_strategy(), _features(), _regime())

    assert result.score == Decimal("100.000000")


@pytest.mark.parametrize(
    ("score", "selected"),
    [
        ("69.999999", False),
        ("70.000000", True),
        ("70.000001", True),
    ],
)
def test_candidate_threshold_is_inclusive(score: str, selected: bool) -> None:
    scored = replace(
        CandidateScorer(POLICY).score(_strategy(), _features(), _regime()),
        score=Decimal(score),
    )
    eligibility = EligibilityResult(
        symbol="AAPL",
        status=EligibilityStatus.ELIGIBLE,
        policy_version="eligibility-policy-v1",
    )

    candidate = CandidateSelector(POLICY).select(eligibility, scored)

    assert (candidate is not None) is selected
    if candidate is not None:
        assert candidate.status == "qualified"
        assert candidate.score == Decimal(score)
        assert candidate.signal_key == scored.signal_key
        assert candidate.input_digest == scored.input_digest
        assert candidate.candidate_key == f"{scored.signal_key}:{POLICY.version}"


@pytest.mark.parametrize(
    ("eligibility_status", "strategy"),
    [
        (EligibilityStatus.INELIGIBLE, _strategy()),
        (EligibilityStatus.BLOCKED, _strategy()),
        (EligibilityStatus.ELIGIBLE, _strategy(status=StrategyStatus.FAILED)),
        (EligibilityStatus.ELIGIBLE, _strategy(status=StrategyStatus.BLOCKED)),
        (
            EligibilityStatus.ELIGIBLE,
            _strategy(gates=(_gate("price_trigger", False),)),
        ),
        (
            EligibilityStatus.ELIGIBLE,
            _strategy(gates=(_gate("regime_compatibility", None),)),
        ),
    ],
)
def test_ineligible_blocked_failed_or_incomplete_results_never_select(
    eligibility_status: EligibilityStatus,
    strategy: StrategyResult,
) -> None:
    scored = replace(strategy, score=Decimal("100"))
    eligibility = EligibilityResult(
        symbol="AAPL",
        status=eligibility_status,
        policy_version="eligibility-policy-v1",
    )

    assert CandidateSelector(POLICY).select(eligibility, scored) is None


def test_selector_rejects_symbol_mismatch_and_unscored_results() -> None:
    eligibility = EligibilityResult(
        symbol="MSFT",
        status=EligibilityStatus.ELIGIBLE,
        policy_version="eligibility-policy-v1",
    )

    assert CandidateSelector(POLICY).select(eligibility, _strategy()) is None
