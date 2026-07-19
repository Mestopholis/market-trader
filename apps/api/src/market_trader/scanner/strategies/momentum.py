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


class _MomentumEvaluator:
    strategy_id: str
    direction: Direction
    trigger_reason: str
    vwap_reason: str

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
            self._trigger_gate(features),
            self._relative_volume_gate(features),
            self._regime_gate(regime),
            self._vwap_gate(features),
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
        values = tuple(observed.values())
        if any(value is None for value in values):
            return _gate(
                "established_trend", None, "feature_input_missing", observed
            )
        decimals = tuple(value for value in values if isinstance(value, Decimal))
        if any(not value.is_finite() for value in decimals):
            return _gate("established_trend", None, "feature_nonfinite", observed)
        close = features.adjusted_close
        sma50 = features.sma_50
        sma200 = features.sma_200
        slope = features.sma_50_slope_20
        if close is None or sma50 is None or sma200 is None or slope is None:
            return _gate(
                "established_trend", None, "feature_input_missing", observed
            )
        if self.direction is Direction.BULLISH:
            passed = close > sma50 > sma200 and slope > 0
        else:
            passed = close < sma50 < sma200 and slope < 0
        return _gate("established_trend", passed, "trend_not_established", observed)

    def _trigger_gate(self, features: FeatureResult) -> GateResult:
        threshold = (
            features.prior_20_high
            if self.direction is Direction.BULLISH
            else features.prior_20_low
        )
        observed = {"session_close": features.session_close, "threshold": threshold}
        if threshold is None:
            return _gate("price_trigger", None, "feature_input_missing", observed)
        if features.session_close is None:
            return _gate(
                "price_trigger", None, "insufficient_intraday_history", observed
            )
        if not threshold.is_finite() or not features.session_close.is_finite():
            return _gate("price_trigger", None, "feature_nonfinite", observed)
        passed = (
            features.session_close > threshold
            if self.direction is Direction.BULLISH
            else features.session_close < threshold
        )
        return _gate("price_trigger", passed, self.trigger_reason, observed)

    def _relative_volume_gate(self, features: FeatureResult) -> GateResult:
        observed = {
            "relative_volume_20": features.relative_volume_20,
            "minimum": self._policy.relative_volume_minimum,
        }
        if features.relative_volume_20 is None:
            return _gate(
                "relative_volume",
                None,
                "insufficient_intraday_history",
                observed,
            )
        if not features.relative_volume_20.is_finite():
            return _gate("relative_volume", None, "feature_nonfinite", observed)
        return _gate(
            "relative_volume",
            features.relative_volume_20 >= self._policy.relative_volume_minimum,
            "relative_volume_below_minimum",
            observed,
        )

    def _regime_gate(self, regime: RegimeResult) -> GateResult:
        observed = {"state": regime.state.value, "signed_score": regime.signed_score}
        if regime.state is RegimeState.BLOCKED:
            return _gate("regime_compatibility", None, "regime_blocked", observed)
        if self.direction is Direction.BULLISH:
            compatible = regime.state is RegimeState.BULLISH or (
                regime.state is RegimeState.MIXED
                and regime.signed_score >= self._policy.mixed_direction_minimum
            )
        else:
            compatible = regime.state is RegimeState.BEARISH or (
                regime.state is RegimeState.MIXED
                and regime.signed_score <= -self._policy.mixed_direction_minimum
            )
        return _gate(
            "regime_compatibility",
            compatible,
            "regime_not_compatible",
            observed,
        )

    def _vwap_gate(self, features: FeatureResult) -> GateResult:
        observed = {
            "session_close": features.session_close,
            "session_vwap": features.session_vwap,
        }
        if features.session_vwap is None:
            return _gate("vwap_position", None, "missing_session_vwap", observed)
        if features.session_close is None:
            return _gate(
                "vwap_position", None, "insufficient_intraday_history", observed
            )
        if not features.session_vwap.is_finite() or not features.session_close.is_finite():
            return _gate("vwap_position", None, "feature_nonfinite", observed)
        passed = (
            features.session_close >= features.session_vwap
            if self.direction is Direction.BULLISH
            else features.session_close <= features.session_vwap
        )
        return _gate("vwap_position", passed, self.vwap_reason, observed)


class BullishBreakoutEvaluator(_MomentumEvaluator):
    strategy_id = "bullish_breakout"
    direction = Direction.BULLISH
    trigger_reason = "breakout_not_confirmed"
    vwap_reason = "price_below_vwap"


class BearishBreakdownEvaluator(_MomentumEvaluator):
    strategy_id = "bearish_breakdown"
    direction = Direction.BEARISH
    trigger_reason = "breakdown_not_confirmed"
    vwap_reason = "price_above_vwap"


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
