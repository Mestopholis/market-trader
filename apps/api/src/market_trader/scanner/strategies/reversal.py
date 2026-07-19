from collections.abc import Mapping
from decimal import Decimal

from market_trader.scanner.configuration import StrategyPolicy
from market_trader.scanner.evidence import SupplementalEvidence
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import (
    Direction,
    GateResult,
    RegimeResult,
    RegimeState,
    StrategyResult,
    StrategyStatus,
)


class _ReversalEvaluator:
    strategy_id: str
    direction: Direction
    zone_reason: str

    def __init__(self, policy: StrategyPolicy) -> None:
        self._policy = policy
        self.version = policy.version

    def evaluate(
        self,
        features: FeatureResult,
        regime: RegimeResult,
        evidence: SupplementalEvidence,
    ) -> StrategyResult:
        del evidence
        gates = (
            self._trend_gate(features),
            self._zone_gate(features),
            self._sma_50_gate(features),
            self._confirmation_gate(features),
            self._regime_gate(regime),
        )
        reasons = tuple(
            sorted({reason for gate in gates for reason in gate.reasons})
        )
        if any(gate.passed is None for gate in gates):
            status = StrategyStatus.BLOCKED
        elif any(gate.passed is False for gate in gates):
            status = StrategyStatus.FAILED
        else:
            status = StrategyStatus.PASSED
        return StrategyResult(
            signal_key=f"{features.symbol}:{self.strategy_id}",
            symbol=features.symbol,
            strategy_id=self.strategy_id,
            policy_version=self.version,
            direction=self.direction,
            status=status,
            gates=gates,
            reasons=reasons,
            lineage=regime.lineage,
        )

    def _trend_gate(self, features: FeatureResult) -> GateResult:
        observed = {
            "adjusted_close": features.adjusted_close,
            "sma_50": features.sma_50,
            "sma_200": features.sma_200,
            "sma_50_slope_20": features.sma_50_slope_20,
        }
        values = (
            features.adjusted_close,
            features.sma_50,
            features.sma_200,
            features.sma_50_slope_20,
        )
        if any(value is None for value in values):
            return _gate(
                "established_trend", None, "feature_input_missing", observed
            )
        if any(value is not None and not value.is_finite() for value in values):
            return _gate("established_trend", None, "feature_nonfinite", observed)
        close, sma50, sma200, slope = values
        if close is None or sma50 is None or sma200 is None or slope is None:
            return _gate(
                "established_trend", None, "feature_input_missing", observed
            )
        passed = (
            close > sma50 > sma200 and slope > 0
            if self.direction is Direction.BULLISH
            else close < sma50 < sma200 and slope < 0
        )
        return _gate("established_trend", passed, "trend_not_established", observed)

    def _zone_gate(self, features: FeatureResult) -> GateResult:
        extreme = (
            features.session_low
            if self.direction is Direction.BULLISH
            else features.session_high
        )
        observed = {
            "session_extreme": extreme,
            "sma_20": features.sma_20,
            "tolerance": self._policy.pullback_tolerance,
        }
        if extreme is None or features.sma_20 is None:
            return _gate("sma_20_zone", None, "feature_input_missing", observed)
        if not extreme.is_finite() or not features.sma_20.is_finite():
            return _gate("sma_20_zone", None, "feature_nonfinite", observed)
        lower = features.sma_20 * (Decimal(1) - self._policy.pullback_tolerance)
        upper = features.sma_20 * (Decimal(1) + self._policy.pullback_tolerance)
        return _gate("sma_20_zone", lower <= extreme <= upper, self.zone_reason, observed)

    def _sma_50_gate(self, features: FeatureResult) -> GateResult:
        extreme = (
            features.session_low
            if self.direction is Direction.BULLISH
            else features.session_high
        )
        observed = {"session_extreme": extreme, "sma_50": features.sma_50}
        if extreme is None or features.sma_50 is None:
            return _gate("sma_50_hold", None, "feature_input_missing", observed)
        if not extreme.is_finite() or not features.sma_50.is_finite():
            return _gate("sma_50_hold", None, "feature_nonfinite", observed)
        passed = (
            extreme > features.sma_50
            if self.direction is Direction.BULLISH
            else extreme < features.sma_50
        )
        return _gate("sma_50_hold", passed, "trend_not_established", observed)

    def _confirmation_gate(self, features: FeatureResult) -> GateResult:
        if len(features.five_minute_bars) < 2:
            return _gate(
                "reversal_confirmation",
                None,
                "insufficient_intraday_history",
                {"completed_five_minute_bars": len(features.five_minute_bars)},
            )
        previous, latest = features.five_minute_bars[-2:]
        observed = {
            "latest_open": latest.open,
            "latest_close": latest.close,
            "previous_high": previous.high,
            "previous_low": previous.low,
        }
        values = (latest.open, latest.close, previous.high, previous.low)
        if any(not value.is_finite() for value in values):
            return _gate(
                "reversal_confirmation", None, "feature_nonfinite", observed
            )
        passed = (
            latest.close > latest.open and latest.close > previous.high
            if self.direction is Direction.BULLISH
            else latest.close < latest.open and latest.close < previous.low
        )
        return _gate(
            "reversal_confirmation", passed, "reversal_not_confirmed", observed
        )

    def _regime_gate(self, regime: RegimeResult) -> GateResult:
        observed = {"state": regime.state.value, "signed_score": regime.signed_score}
        if regime.state is RegimeState.BLOCKED:
            return _gate("regime_compatibility", None, "regime_blocked", observed)
        if self.direction is Direction.BULLISH:
            compatible = (
                regime.state is RegimeState.BULLISH
                or (regime.state is RegimeState.NEUTRAL and regime.signed_score >= 0)
                or (regime.state is RegimeState.MIXED and regime.signed_score > 0)
            )
        else:
            compatible = (
                regime.state is RegimeState.BEARISH
                or (regime.state is RegimeState.NEUTRAL and regime.signed_score <= 0)
                or (regime.state is RegimeState.MIXED and regime.signed_score < 0)
            )
        return _gate(
            "regime_compatibility",
            compatible,
            "regime_not_compatible",
            observed,
        )


class BullishPullbackEvaluator(_ReversalEvaluator):
    strategy_id = "bullish_pullback"
    direction = Direction.BULLISH
    zone_reason = "pullback_zone_not_reached"


class BearishFailedRallyEvaluator(_ReversalEvaluator):
    strategy_id = "bearish_failed_rally"
    direction = Direction.BEARISH
    zone_reason = "failed_rally_zone_not_reached"


def _gate(
    name: str,
    passed: bool | None,
    failure_reason: str,
    observed: Mapping[str, object],
) -> GateResult:
    return GateResult(
        name=name,
        passed=passed,
        reasons=() if passed is True else (failure_reason,),
        observed=observed,
    )
