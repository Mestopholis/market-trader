from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.scanner.configuration import StrategyPolicy
from market_trader.scanner.evidence import (
    CatalystDirection,
    CatalystEvidence,
    CatalystMateriality,
    SupplementalEvidence,
)
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import (
    Direction,
    GateResult,
    RegimeResult,
    RegimeState,
    StrategyResult,
    StrategyStatus,
)

_XNYS_TIMEZONE = ZoneInfo("America/New_York")


class NewsContinuationEvaluator:
    strategy_id = "news_continuation"

    def __init__(self, policy: StrategyPolicy) -> None:
        self._policy = policy
        self.version = policy.version

    def evaluate(
        self,
        features: FeatureResult,
        regime: RegimeResult,
        evidence: SupplementalEvidence,
    ) -> StrategyResult:
        catalysts = tuple(
            sorted(
                (catalyst for catalyst in evidence.catalysts if catalyst.symbol == features.symbol),
                key=_catalyst_sort_key,
            )
        )
        lineage = tuple(
            sorted({catalyst.lineage_id for catalyst in catalysts} | set(regime.lineage))
        )
        if not catalysts:
            return self._terminal_result(
                features,
                regime,
                Direction.BULLISH,
                StrategyStatus.NOT_APPLICABLE,
                "catalyst_missing",
                lineage,
            )

        malformed_reason = self._malformed_reason(catalysts, evidence.as_of)
        if malformed_reason is not None:
            return self._terminal_result(
                features,
                regime,
                Direction.BULLISH,
                StrategyStatus.BLOCKED,
                malformed_reason,
                lineage,
            )

        deduplicated, duplicate_reason, duplicate_conflict = _deduplicate(catalysts)
        if duplicate_conflict:
            return self._terminal_result(
                features,
                regime,
                Direction.BULLISH,
                StrategyStatus.BLOCKED,
                "duplicate_evidence_lineage",
                lineage,
            )

        material = tuple(
            catalyst
            for catalyst in deduplicated
            if catalyst.materiality is CatalystMateriality.MATERIAL
        )
        if not material:
            return self._terminal_result(
                features,
                regime,
                Direction.BULLISH,
                StrategyStatus.NOT_APPLICABLE,
                "catalyst_not_material",
                lineage,
            )

        clear_directions = {
            catalyst.direction
            for catalyst in material
            if catalyst.direction is not CatalystDirection.UNCLEAR
        }
        if len(clear_directions) > 1:
            return self._terminal_result(
                features,
                regime,
                Direction.BULLISH,
                StrategyStatus.BLOCKED,
                "conflicting_catalyst_direction",
                lineage,
            )
        if not clear_directions:
            return self._terminal_result(
                features,
                regime,
                Direction.BULLISH,
                StrategyStatus.FAILED,
                "catalyst_direction_unclear",
                lineage,
            )

        catalyst_direction = next(iter(clear_directions))
        direction = (
            Direction.BULLISH
            if catalyst_direction is CatalystDirection.POSITIVE
            else Direction.BEARISH
        )
        gates = (
            _gate(
                "material_catalyst",
                True,
                "catalyst_missing",
                {"direction": catalyst_direction.value},
            ),
            self._vwap_gate(features, direction),
            self._relative_volume_gate(features),
            self._session_open_gate(features, direction),
            self._regime_gate(regime, direction),
        )
        reasons = {reason for gate in gates for reason in gate.reasons}
        if duplicate_reason:
            reasons.add("duplicate_evidence_lineage")
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
            direction=direction,
            status=status,
            gates=gates,
            reasons=tuple(sorted(reasons)),
            lineage=lineage,
        )

    def _malformed_reason(
        self,
        catalysts: tuple[CatalystEvidence, ...],
        as_of: datetime,
    ) -> str | None:
        reference = ensure_utc(as_of)
        cutoff = _catalyst_cutoff(
            reference.astimezone(_XNYS_TIMEZONE).date(),
            self._policy.catalyst_lookback_completed_sessions,
        )
        for catalyst in catalysts:
            if not catalyst.source.strip() or not catalyst.source_reference.strip():
                return "catalyst_missing"
            timestamps = (
                catalyst.observed_at,
                catalyst.valid_until,
                catalyst.published_at,
            )
            try:
                observed_at, valid_until, published_at = map(ensure_utc, timestamps)
            except ValueError:
                return "catalyst_stale"
            if (
                observed_at > reference
                or valid_until < reference
                or valid_until < observed_at
                or published_at > observed_at
                or published_at < cutoff
            ):
                return "catalyst_stale"
        return None

    def _vwap_gate(self, features: FeatureResult, direction: Direction) -> GateResult:
        observed = {
            "session_close": features.session_close,
            "session_vwap": features.session_vwap,
        }
        if features.session_vwap is None:
            return _gate("vwap_position", None, "missing_session_vwap", observed)
        if features.session_close is None:
            return _gate("vwap_position", None, "insufficient_intraday_history", observed)
        if not features.session_close.is_finite() or not features.session_vwap.is_finite():
            return _gate("vwap_position", None, "feature_nonfinite", observed)
        passed = (
            features.session_close > features.session_vwap
            if direction is Direction.BULLISH
            else features.session_close < features.session_vwap
        )
        reason = "price_below_vwap" if direction is Direction.BULLISH else "price_above_vwap"
        return _gate("vwap_position", passed, reason, observed)

    def _relative_volume_gate(self, features: FeatureResult) -> GateResult:
        observed = {
            "relative_volume_20": features.relative_volume_20,
            "minimum": self._policy.relative_volume_minimum,
        }
        if features.relative_volume_20 is None:
            return _gate("relative_volume", None, "insufficient_intraday_history", observed)
        if not features.relative_volume_20.is_finite():
            return _gate("relative_volume", None, "feature_nonfinite", observed)
        return _gate(
            "relative_volume",
            features.relative_volume_20 >= self._policy.relative_volume_minimum,
            "relative_volume_below_minimum",
            observed,
        )

    def _session_open_gate(self, features: FeatureResult, direction: Direction) -> GateResult:
        observed = {
            "session_close": features.session_close,
            "session_open": features.session_open,
        }
        if features.session_close is None or features.session_open is None:
            return _gate("session_open_hold", None, "insufficient_intraday_history", observed)
        if not features.session_close.is_finite() or not features.session_open.is_finite():
            return _gate("session_open_hold", None, "feature_nonfinite", observed)
        passed = (
            features.session_close > features.session_open
            if direction is Direction.BULLISH
            else features.session_close < features.session_open
        )
        return _gate("session_open_hold", passed, "session_open_not_held", observed)

    def _regime_gate(self, regime: RegimeResult, direction: Direction) -> GateResult:
        observed = {"state": regime.state.value, "signed_score": regime.signed_score}
        if regime.state is RegimeState.BLOCKED:
            return _gate("regime_compatibility", None, "regime_blocked", observed)
        threshold = self._policy.news_regime_opposition_block_threshold
        compatible = (
            regime.signed_score > -threshold
            if direction is Direction.BULLISH
            else regime.signed_score < threshold
        )
        return _gate("regime_compatibility", compatible, "regime_not_compatible", observed)

    def _terminal_result(
        self,
        features: FeatureResult,
        regime: RegimeResult,
        direction: Direction,
        status: StrategyStatus,
        reason: str,
        lineage: tuple[str, ...],
    ) -> StrategyResult:
        return StrategyResult(
            signal_key=f"{features.symbol}:{self.strategy_id}",
            symbol=features.symbol,
            strategy_id=self.strategy_id,
            policy_version=self.version,
            direction=direction,
            status=status,
            gates=(
                _gate(
                    "material_catalyst",
                    None if status is StrategyStatus.BLOCKED else False,
                    reason,
                    {},
                ),
            ),
            reasons=(reason,),
            lineage=lineage,
        )


def _deduplicate(
    catalysts: tuple[CatalystEvidence, ...],
) -> tuple[tuple[CatalystEvidence, ...], bool, bool]:
    grouped: dict[str, list[CatalystEvidence]] = defaultdict(list)
    for catalyst in catalysts:
        grouped[catalyst.lineage_id].append(catalyst)

    deduplicated: list[CatalystEvidence] = []
    duplicate = False
    for lineage_id in sorted(grouped):
        group = grouped[lineage_id]
        fingerprints = {_catalyst_fingerprint(catalyst) for catalyst in group}
        if len(fingerprints) > 1:
            return (), True, True
        duplicate = duplicate or len(group) > 1
        deduplicated.append(min(group, key=_catalyst_sort_key))
    return tuple(deduplicated), duplicate, False


def _catalyst_fingerprint(catalyst: CatalystEvidence) -> tuple[object, ...]:
    return (
        catalyst.schema_version,
        catalyst.configuration_version,
        catalyst.correlation_id,
        catalyst.lineage_id,
        catalyst.source,
        catalyst.observed_at,
        catalyst.valid_until,
        catalyst.symbol,
        catalyst.source_reference,
        catalyst.published_at,
        catalyst.materiality,
        catalyst.direction,
        catalyst.category,
    )


def _catalyst_sort_key(catalyst: CatalystEvidence) -> tuple[str, ...]:
    return (
        catalyst.lineage_id,
        catalyst.evidence_id,
        catalyst.direction.value,
        catalyst.published_at.isoformat(),
    )


@lru_cache(maxsize=64)
def _catalyst_cutoff(session_date: date, completed_sessions: int) -> datetime:
    calendar = XNYSCalendarAdapter(
        start=session_date - timedelta(days=max(14, completed_sessions * 7 + 7)),
        end=session_date + timedelta(days=1),
    )
    previous = session_date
    session = calendar.previous_session(previous)
    for _ in range(1, completed_sessions):
        session = calendar.previous_session(session.session_date)
    return session.market_open


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
