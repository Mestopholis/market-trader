from dataclasses import replace
from decimal import Decimal

from market_trader.scanner.configuration import ScoringPolicy
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import (
    CandidateResult,
    ComponentScore,
    Direction,
    EligibilityResult,
    EligibilityStatus,
    GateResult,
    RegimeResult,
    RegimeState,
    StrategyResult,
    StrategyStatus,
)

_ZERO = Decimal(0)
_ONE_HUNDRED = Decimal(100)
_REVERSAL_STRATEGIES = {"bullish_pullback", "bearish_failed_rally"}


class CandidateScorer:
    version = "candidate-scoring-v1"

    def __init__(self, policy: ScoringPolicy) -> None:
        self._policy = policy
        self.version = policy.version

    def score(
        self,
        strategy: StrategyResult,
        features: FeatureResult,
        regime: RegimeResult,
    ) -> StrategyResult:
        if strategy.symbol != features.symbol:
            raise ValueError("strategy and features must describe the same symbol")

        feature_lineage = tuple(
            sorted({reference.lineage_id for reference in strategy.input_references})
        )
        regime_lineage = tuple(sorted(set(regime.lineage)))
        catalyst_lineage = tuple(sorted(set(strategy.lineage) - set(regime.lineage)))
        raw_scores = {
            "market_direction": self._market_direction(strategy, regime),
            "price_structure": self._price_structure(strategy, features),
            "participation_liquidity": self._participation(features),
            "relative_performance": self._relative_performance(strategy, features),
            "catalyst": self._catalyst(strategy),
        }
        family_lineage = {
            "market_direction": regime_lineage,
            "price_structure": feature_lineage,
            "participation_liquidity": feature_lineage,
            "relative_performance": feature_lineage,
            "catalyst": catalyst_lineage,
        }
        components = tuple(
            ComponentScore(
                family=family,
                pre_cap=points,
                cap=self._policy.family_caps[family],
                final=min(max(points, _ZERO), self._policy.family_caps[family]),
                lineage=family_lineage[family],
            )
            for family, points in raw_scores.items()
        )
        total = sum((component.final for component in components), start=_ZERO)
        total = min(max(total, _ZERO), _ONE_HUNDRED).quantize(self._policy.score_quantum)
        return replace(strategy, components=components, score=total)

    def _market_direction(self, strategy: StrategyResult, regime: RegimeResult) -> Decimal:
        points = _ZERO
        if _gate_passed(strategy.gates, "established_trend"):
            points += self._points("established_trend")
        aligned = (
            strategy.direction is Direction.BULLISH and regime.state is RegimeState.BULLISH
        ) or (strategy.direction is Direction.BEARISH and regime.state is RegimeState.BEARISH)
        if aligned:
            points += self._points("aligned_regime")
        elif regime.state is RegimeState.NEUTRAL and strategy.strategy_id in _REVERSAL_STRATEGIES:
            points += self._points("neutral_reversal_regime")
        elif regime.state is RegimeState.MIXED and _signed_compatible(
            strategy.direction, regime.signed_score
        ):
            points += self._points("mixed_compatible_regime")
        return points

    def _price_structure(self, strategy: StrategyResult, features: FeatureResult) -> Decimal:
        trigger_name = _trigger_gate_name(strategy.strategy_id)
        trigger_passed = _gate_passed(strategy.gates, trigger_name)
        points = self._points("price_trigger") if trigger_passed else _ZERO
        if trigger_passed and self._has_price_extension(strategy, features):
            points += self._points("price_extension")
        if _correct_vwap_side(strategy.direction, features):
            points += self._points("correct_vwap_side")
        return points

    def _has_price_extension(self, strategy: StrategyResult, features: FeatureResult) -> bool:
        if strategy.strategy_id == "news_continuation":
            return _directional_distance(
                strategy.direction,
                features.session_close,
                features.session_vwap,
                self._policy.price_extension_minimum,
            )
        if strategy.strategy_id in {"bullish_breakout", "bearish_breakdown"}:
            threshold = (
                features.prior_20_high
                if strategy.direction is Direction.BULLISH
                else features.prior_20_low
            )
            return _directional_distance(
                strategy.direction,
                features.session_close,
                threshold,
                self._policy.price_extension_minimum,
            )
        if strategy.strategy_id in _REVERSAL_STRATEGIES:
            if len(features.five_minute_bars) < 2:
                return False
            previous, latest = features.five_minute_bars[-2:]
            threshold = previous.high if strategy.direction is Direction.BULLISH else previous.low
            return _directional_distance(
                strategy.direction,
                latest.close,
                threshold,
                self._policy.price_extension_minimum,
            )
        return False

    def _participation(self, features: FeatureResult) -> Decimal:
        points = _ZERO
        dollar_volume = features.median_dollar_volume_20
        if dollar_volume is not None and dollar_volume.is_finite() and dollar_volume > 0:
            points += self._points("eligibility_liquidity")
        relative_volume = features.relative_volume_20
        if relative_volume is None or not relative_volume.is_finite():
            return points
        if relative_volume >= self._policy.relative_volume_high_minimum:
            points += self._points("relative_volume_high")
        elif relative_volume >= self._policy.relative_volume_standard_minimum:
            points += self._points("relative_volume_standard")
        return points

    def _relative_performance(self, strategy: StrategyResult, features: FeatureResult) -> Decimal:
        percentile = features.relative_strength_percentile_20
        if percentile is None or not percentile.is_finite():
            return _ZERO
        if strategy.direction is Direction.BULLISH:
            if percentile >= self._policy.relative_strength_bullish_exceptional_minimum:
                return self._points("relative_strength_exceptional")
            if percentile >= self._policy.relative_strength_bullish_standard_minimum:
                return self._points("relative_strength_standard")
        else:
            if percentile <= self._policy.relative_strength_bearish_exceptional_maximum:
                return self._points("relative_strength_exceptional")
            if percentile <= self._policy.relative_strength_bearish_standard_maximum:
                return self._points("relative_strength_standard")
        return _ZERO

    def _catalyst(self, strategy: StrategyResult) -> Decimal:
        if strategy.strategy_id == "news_continuation" and _gate_passed(
            strategy.gates, "material_catalyst"
        ):
            return self._points("compatible_catalyst")
        return _ZERO

    def _points(self, name: str) -> Decimal:
        return self._policy.component_points[name]


class CandidateSelector:
    def __init__(self, policy: ScoringPolicy) -> None:
        self._policy = policy
        self.version = policy.version

    def select(
        self,
        eligibility: EligibilityResult,
        scored: StrategyResult,
    ) -> CandidateResult | None:
        if eligibility.symbol != scored.symbol:
            return None
        if eligibility.status is not EligibilityStatus.ELIGIBLE:
            return None
        if scored.status is not StrategyStatus.PASSED or scored.score is None:
            return None
        if any(gate.required and gate.passed is not True for gate in scored.gates):
            return None
        if scored.score < self._policy.candidate_threshold:
            return None
        return CandidateResult(
            candidate_key=f"{scored.signal_key}:{self.version}",
            signal_key=scored.signal_key,
            symbol=scored.symbol,
            strategy_id=scored.strategy_id,
            direction=scored.direction,
            score=scored.score,
            reasons=scored.reasons,
            input_digest=scored.input_digest,
        )


def _gate_passed(gates: tuple[GateResult, ...], name: str) -> bool:
    return any(gate.name == name and gate.passed is True for gate in gates)


def _trigger_gate_name(strategy_id: str) -> str:
    if strategy_id in _REVERSAL_STRATEGIES:
        return "reversal_confirmation"
    if strategy_id == "news_continuation":
        return "session_open_hold"
    return "price_trigger"


def _correct_vwap_side(direction: Direction, features: FeatureResult) -> bool:
    return _directional_distance(
        direction,
        features.session_close,
        features.session_vwap,
        _ZERO,
    )


def _directional_distance(
    direction: Direction,
    value: Decimal | None,
    threshold: Decimal | None,
    minimum: Decimal,
) -> bool:
    if (
        value is None
        or threshold is None
        or not value.is_finite()
        or not threshold.is_finite()
        or threshold == 0
    ):
        return False
    distance = (
        (value - threshold) / threshold
        if direction is Direction.BULLISH
        else (threshold - value) / threshold
    )
    return distance > 0 and distance >= minimum


def _signed_compatible(direction: Direction, score: Decimal) -> bool:
    return score > 0 if direction is Direction.BULLISH else score < 0
