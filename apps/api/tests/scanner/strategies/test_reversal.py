from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.evidence import SupplementalEvidence
from market_trader.scanner.features import FeatureResult, FiveMinuteBar
from market_trader.scanner.models import RegimeResult, RegimeState, StrategyStatus
from market_trader.scanner.strategies import (
    BearishFailedRallyEvaluator,
    BullishPullbackEvaluator,
)

CONFIGURATION_PATH = Path(__file__).parents[3] / "config" / "scanner"
POLICY = load_scanner_configuration(CONFIGURATION_PATH).strategies
AS_OF = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)
EVIDENCE = SupplementalEvidence(
    as_of=AS_OF,
    breadth=(),
    sector=(),
    volatility=(),
    macro=(),
    catalysts=(),
)


def _bar(
    index: int,
    *,
    open_price: str,
    high: str,
    low: str,
    close: str,
) -> FiveMinuteBar:
    start = AS_OF - timedelta(minutes=10 - index * 5)
    return FiveMinuteBar(
        start=start,
        end=start + timedelta(minutes=5),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1_000,
    )


def _bullish_features(*, session_low: Decimal = Decimal("100")) -> FeatureResult:
    return FeatureResult(
        symbol="AAPL",
        adjusted_close=Decimal("110"),
        sma_20=Decimal("100"),
        sma_50=Decimal("95"),
        sma_200=Decimal("90"),
        sma_50_slope_20=Decimal("0.01"),
        session_low=session_low,
        five_minute_bars=(
            _bar(0, open_price="101", high="104", low="100", close="102"),
            _bar(1, open_price="103", high="106", low="102", close="105"),
        ),
    )


def _bearish_features(*, session_high: Decimal = Decimal("100")) -> FeatureResult:
    return FeatureResult(
        symbol="AAPL",
        adjusted_close=Decimal("90"),
        sma_20=Decimal("100"),
        sma_50=Decimal("105"),
        sma_200=Decimal("110"),
        sma_50_slope_20=Decimal("-0.01"),
        session_high=session_high,
        five_minute_bars=(
            _bar(0, open_price="99", high="100", low="96", close="98"),
            _bar(1, open_price="97", high="98", low="94", close="95"),
        ),
    )


def _regime(state: RegimeState, score: str) -> RegimeResult:
    return RegimeResult(
        state=state,
        signed_score=Decimal(score),
        policy_version="market-regime-v1",
        lineage=("regime-lineage",),
    )


@pytest.mark.parametrize("session_low", [Decimal("99"), Decimal("101")])
def test_bullish_pullback_accepts_exact_one_percent_boundaries(
    session_low: Decimal,
) -> None:
    result = BullishPullbackEvaluator(POLICY).evaluate(
        _bullish_features(session_low=session_low),
        _regime(RegimeState.BULLISH, "35"),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.PASSED
    assert result.reasons == ()


@pytest.mark.parametrize("session_high", [Decimal("99"), Decimal("101")])
def test_bearish_failed_rally_accepts_exact_one_percent_boundaries(
    session_high: Decimal,
) -> None:
    result = BearishFailedRallyEvaluator(POLICY).evaluate(
        _bearish_features(session_high=session_high),
        _regime(RegimeState.BEARISH, "-35"),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.PASSED
    assert result.reasons == ()


@pytest.mark.parametrize(
    ("features", "reason"),
    [
        (_bullish_features(session_low=Decimal("98.999999")), "pullback_zone_not_reached"),
        (
            replace(
                _bullish_features(session_low=Decimal("99")),
                sma_50=Decimal("99"),
            ),
            "trend_not_established",
        ),
        (
            replace(
                _bullish_features(),
                five_minute_bars=(
                    _bullish_features().five_minute_bars[0],
                    replace(
                        _bullish_features().five_minute_bars[1],
                        close=Decimal("103"),
                    ),
                ),
            ),
            "reversal_not_confirmed",
        ),
        (
            replace(
                _bullish_features(),
                five_minute_bars=(
                    _bullish_features().five_minute_bars[0],
                    replace(
                        _bullish_features().five_minute_bars[1],
                        close=Decimal("104"),
                    ),
                ),
            ),
            "reversal_not_confirmed",
        ),
    ],
)
def test_bullish_completed_false_gates_fail(features: FeatureResult, reason: str) -> None:
    result = BullishPullbackEvaluator(POLICY).evaluate(
        features,
        _regime(RegimeState.BULLISH, "35"),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.FAILED
    assert reason in result.reasons


@pytest.mark.parametrize(
    ("features", "reason"),
    [
        (_bearish_features(session_high=Decimal("101.000001")), "failed_rally_zone_not_reached"),
        (
            replace(
                _bearish_features(session_high=Decimal("101")),
                sma_50=Decimal("101"),
            ),
            "trend_not_established",
        ),
        (
            replace(
                _bearish_features(),
                five_minute_bars=(
                    _bearish_features().five_minute_bars[0],
                    replace(
                        _bearish_features().five_minute_bars[1],
                        close=Decimal("97"),
                    ),
                ),
            ),
            "reversal_not_confirmed",
        ),
        (
            replace(
                _bearish_features(),
                five_minute_bars=(
                    _bearish_features().five_minute_bars[0],
                    replace(
                        _bearish_features().five_minute_bars[1],
                        close=Decimal("96"),
                    ),
                ),
            ),
            "reversal_not_confirmed",
        ),
    ],
)
def test_bearish_completed_false_gates_fail(features: FeatureResult, reason: str) -> None:
    result = BearishFailedRallyEvaluator(POLICY).evaluate(
        features,
        _regime(RegimeState.BEARISH, "-35"),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.FAILED
    assert reason in result.reasons


@pytest.mark.parametrize("bars", [(), (_bullish_features().five_minute_bars[0],)])
def test_missing_completed_aggregates_block(
    bars: tuple[FiveMinuteBar, ...],
) -> None:
    result = BullishPullbackEvaluator(POLICY).evaluate(
        replace(_bullish_features(), five_minute_bars=bars),
        _regime(RegimeState.BULLISH, "35"),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.BLOCKED
    assert "insufficient_intraday_history" in result.reasons


@pytest.mark.parametrize(
    ("evaluator", "features", "state", "score", "status"),
    [
        (
            BullishPullbackEvaluator(POLICY),
            _bullish_features(),
            RegimeState.NEUTRAL,
            "0",
            StrategyStatus.PASSED,
        ),
        (
            BullishPullbackEvaluator(POLICY),
            _bullish_features(),
            RegimeState.NEUTRAL,
            "-0.000001",
            StrategyStatus.FAILED,
        ),
        (
            BullishPullbackEvaluator(POLICY),
            _bullish_features(),
            RegimeState.MIXED,
            "0.000001",
            StrategyStatus.PASSED,
        ),
        (
            BullishPullbackEvaluator(POLICY),
            _bullish_features(),
            RegimeState.MIXED,
            "0",
            StrategyStatus.FAILED,
        ),
        (
            BearishFailedRallyEvaluator(POLICY),
            _bearish_features(),
            RegimeState.NEUTRAL,
            "0",
            StrategyStatus.PASSED,
        ),
        (
            BearishFailedRallyEvaluator(POLICY),
            _bearish_features(),
            RegimeState.NEUTRAL,
            "0.000001",
            StrategyStatus.FAILED,
        ),
        (
            BearishFailedRallyEvaluator(POLICY),
            _bearish_features(),
            RegimeState.MIXED,
            "-0.000001",
            StrategyStatus.PASSED,
        ),
        (
            BearishFailedRallyEvaluator(POLICY),
            _bearish_features(),
            RegimeState.MIXED,
            "0",
            StrategyStatus.FAILED,
        ),
    ],
)
def test_neutral_and_mixed_regimes_require_directional_compatibility(
    evaluator: BullishPullbackEvaluator | BearishFailedRallyEvaluator,
    features: FeatureResult,
    state: RegimeState,
    score: str,
    status: StrategyStatus,
) -> None:
    result = evaluator.evaluate(features, _regime(state, score), EVIDENCE)

    assert result.status is status


def test_blocked_regime_and_missing_feature_block_with_stable_gates() -> None:
    result = BullishPullbackEvaluator(POLICY).evaluate(
        replace(_bullish_features(), sma_20=None),
        _regime(RegimeState.BLOCKED, "0"),
        EVIDENCE,
    )

    assert result.status is StrategyStatus.BLOCKED
    assert result.reasons == (
        "feature_input_missing",
        "regime_blocked",
    )
    assert tuple(gate.name for gate in result.gates) == (
        "established_trend",
        "regime_compatibility",
        "reversal_confirmation",
        "sma_20_zone",
        "sma_50_hold",
    )
