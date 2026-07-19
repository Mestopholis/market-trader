from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.evidence import SupplementalEvidence
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import RegimeResult, RegimeState, StrategyStatus
from market_trader.scanner.strategies import (
    BearishBreakdownEvaluator,
    BullishBreakoutEvaluator,
    StrategyEvaluator,
)

CONFIGURATION_PATH = Path(__file__).parents[3] / "config" / "scanner"
POLICY = load_scanner_configuration(CONFIGURATION_PATH).strategies
EVIDENCE = SupplementalEvidence(
    as_of=datetime(2026, 7, 17, 15, 35, tzinfo=UTC),
    breadth=(),
    sector=(),
    volatility=(),
    macro=(),
    catalysts=(),
)


def _bullish_features() -> FeatureResult:
    return FeatureResult(
        symbol="AAPL",
        adjusted_close=Decimal("110"),
        sma_50=Decimal("105"),
        sma_200=Decimal("100"),
        sma_50_slope_20=Decimal("0.01"),
        prior_20_high=Decimal("108"),
        session_close=Decimal("110"),
        session_vwap=Decimal("110"),
        relative_volume_20=Decimal("1.50"),
    )


def _bearish_features() -> FeatureResult:
    return FeatureResult(
        symbol="AAPL",
        adjusted_close=Decimal("90"),
        sma_50=Decimal("95"),
        sma_200=Decimal("100"),
        sma_50_slope_20=Decimal("-0.01"),
        prior_20_low=Decimal("92"),
        session_close=Decimal("90"),
        session_vwap=Decimal("90"),
        relative_volume_20=Decimal("1.50"),
    )


def _regime(state: RegimeState, score: Decimal) -> RegimeResult:
    return RegimeResult(
        state=state,
        signed_score=score,
        policy_version="market-regime-v1",
        lineage=("regime-z", "regime-a"),
    )


def _changed(
    features: FeatureResult, changes: dict[str, object]
) -> FeatureResult:
    return replace(features, **cast(Any, changes))


@pytest.mark.parametrize(
    ("evaluator", "features", "regime"),
    [
        (
            BullishBreakoutEvaluator(POLICY),
            _bullish_features(),
            _regime(RegimeState.BULLISH, Decimal("35")),
        ),
        (
            BearishBreakdownEvaluator(POLICY),
            _bearish_features(),
            _regime(RegimeState.BEARISH, Decimal("-35")),
        ),
    ],
)
def test_momentum_strategies_pass_inclusive_boundaries(
    evaluator: StrategyEvaluator,
    features: FeatureResult,
    regime: RegimeResult,
) -> None:
    result = evaluator.evaluate(features, regime, EVIDENCE)

    assert result.status is StrategyStatus.PASSED
    assert result.reasons == ()
    assert result.score is None
    assert all(gate.passed is True for gate in result.gates)
    assert result.lineage == ("regime-a", "regime-z")
    assert result.strategy_id == evaluator.strategy_id
    assert result.policy_version == "scanner-strategies-v1"
    assert result.signal_key == f"AAPL:{evaluator.strategy_id}"


@pytest.mark.parametrize(
    ("changes", "regime", "reason"),
    [
        ({"sma_50_slope_20": Decimal("0")}, None, "trend_not_established"),
        ({"session_close": Decimal("108")}, None, "breakout_not_confirmed"),
        (
            {"relative_volume_20": Decimal("1.49")},
            None,
            "relative_volume_below_minimum",
        ),
        ({"session_vwap": Decimal("111")}, None, "price_below_vwap"),
        ({}, _regime(RegimeState.NEUTRAL, Decimal("0")), "regime_not_compatible"),
    ],
)
def test_bullish_completed_false_gates_fail(
    changes: dict[str, object], regime: RegimeResult | None, reason: str
) -> None:
    result = BullishBreakoutEvaluator(POLICY).evaluate(
        _changed(_bullish_features(), changes),
        regime or _regime(RegimeState.BULLISH, Decimal("35")),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.FAILED
    assert reason in result.reasons


@pytest.mark.parametrize(
    ("changes", "regime", "reason"),
    [
        ({"sma_50_slope_20": Decimal("0")}, None, "trend_not_established"),
        ({"session_close": Decimal("92")}, None, "breakdown_not_confirmed"),
        (
            {"relative_volume_20": Decimal("1.49")},
            None,
            "relative_volume_below_minimum",
        ),
        ({"session_vwap": Decimal("89")}, None, "price_above_vwap"),
        ({}, _regime(RegimeState.NEUTRAL, Decimal("0")), "regime_not_compatible"),
    ],
)
def test_bearish_completed_false_gates_fail(
    changes: dict[str, object], regime: RegimeResult | None, reason: str
) -> None:
    result = BearishBreakdownEvaluator(POLICY).evaluate(
        _changed(_bearish_features(), changes),
        regime or _regime(RegimeState.BEARISH, Decimal("-35")),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.FAILED
    assert reason in result.reasons


@pytest.mark.parametrize(
    ("changes", "regime", "reason"),
    [
        ({"adjusted_close": None}, None, "feature_input_missing"),
        ({"prior_20_high": None}, None, "feature_input_missing"),
        ({"relative_volume_20": None}, None, "insufficient_intraday_history"),
        ({"session_vwap": None}, None, "missing_session_vwap"),
        (
            {},
            _regime(RegimeState.BLOCKED, Decimal("0")),
            "regime_blocked",
        ),
    ],
)
def test_unavailable_bullish_inputs_block(
    changes: dict[str, object], regime: RegimeResult | None, reason: str
) -> None:
    result = BullishBreakoutEvaluator(POLICY).evaluate(
        _changed(_bullish_features(), changes),
        regime or _regime(RegimeState.BULLISH, Decimal("35")),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.BLOCKED
    assert reason in result.reasons
    assert any(gate.passed is None for gate in result.gates)


@pytest.mark.parametrize(
    ("evaluator", "features", "score", "status"),
    [
        (
            BullishBreakoutEvaluator(POLICY),
            _bullish_features(),
            Decimal("20"),
            StrategyStatus.PASSED,
        ),
        (
            BullishBreakoutEvaluator(POLICY),
            _bullish_features(),
            Decimal("19.999999"),
            StrategyStatus.FAILED,
        ),
        (
            BearishBreakdownEvaluator(POLICY),
            _bearish_features(),
            Decimal("-20"),
            StrategyStatus.PASSED,
        ),
        (
            BearishBreakdownEvaluator(POLICY),
            _bearish_features(),
            Decimal("-19.999999"),
            StrategyStatus.FAILED,
        ),
    ],
)
def test_mixed_regime_direction_threshold_is_inclusive(
    evaluator: StrategyEvaluator,
    features: FeatureResult,
    score: Decimal,
    status: StrategyStatus,
) -> None:
    result = evaluator.evaluate(
        features,
        _regime(RegimeState.MIXED, score),
        EVIDENCE,
    )

    assert result.status is status


def test_multiple_failures_and_gates_are_stably_ordered() -> None:
    result = BullishBreakoutEvaluator(POLICY).evaluate(
        replace(
            _bullish_features(),
            sma_50_slope_20=Decimal("0"),
            session_close=Decimal("107"),
            relative_volume_20=Decimal("1"),
            session_vwap=Decimal("111"),
        ),
        _regime(RegimeState.NEUTRAL, Decimal("0")),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.FAILED
    assert result.reasons == (
        "breakout_not_confirmed",
        "price_below_vwap",
        "regime_not_compatible",
        "relative_volume_below_minimum",
        "trend_not_established",
    )
    assert tuple(gate.name for gate in result.gates) == (
        "established_trend",
        "price_trigger",
        "regime_compatibility",
        "relative_volume",
        "vwap_position",
    )
