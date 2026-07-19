from collections.abc import Sequence
from decimal import Decimal

from market_trader.scanner.configuration import RegimePolicy
from market_trader.scanner.evidence import (
    BreadthEvidence,
    EvidenceMetadata,
    MacroEvidence,
    MacroState,
    SectorEvidence,
    SupplementalEvidence,
    VolatilityDirection,
    VolatilityEvidence,
)
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import RegimeResult, RegimeState

_BLOCKING_REASONS = frozenset(
    {
        "macro_blocked",
        "regime_input_conflicting",
        "regime_input_missing",
        "regime_input_stale",
    }
)


class RegimeClassifier:
    def __init__(self, policy: RegimePolicy) -> None:
        self._policy = policy
        self.version = policy.version

    def classify(
        self,
        broad_features: Sequence[FeatureResult],
        evidence: SupplementalEvidence,
    ) -> RegimeResult:
        reasons: set[str] = set()
        lineage: set[str] = set()
        spy = self._spy_features(broad_features, reasons)
        breadth = self._critical_record(evidence.breadth, evidence, reasons, lineage)
        sector = self._critical_record(evidence.sector, evidence, reasons, lineage)
        volatility = self._critical_record(
            evidence.volatility, evidence, reasons, lineage
        )
        macro = self._critical_record(evidence.macro, evidence, reasons, lineage)

        components = {
            "broad_trend": self._broad_trend(spy, reasons),
            "breadth": self._breadth(breadth, reasons),
            "sector_participation": self._sector_participation(sector, reasons),
            "volume_participation": self._volume_participation(breadth, reasons),
            "volatility_direction": self._volatility(volatility, reasons),
            "macro_overlay": self._macro(macro, reasons),
        }
        signed_score = sum(components.values(), Decimal())
        state = self._state(components, signed_score, sector, reasons)
        return RegimeResult(
            state=state,
            signed_score=signed_score,
            policy_version=self.version,
            components=components,
            reasons=tuple(sorted(reasons)),
            lineage=tuple(sorted(lineage)),
        )

    def _spy_features(
        self, features: Sequence[FeatureResult], reasons: set[str]
    ) -> FeatureResult | None:
        matches = tuple(item for item in features if item.symbol == "SPY")
        if not matches:
            reasons.add("regime_input_missing")
            return None
        if len(matches) != 1:
            reasons.add("regime_input_conflicting")
            return None
        required = (
            matches[0].adjusted_close,
            matches[0].sma_50,
            matches[0].sma_200,
            matches[0].sma_50_slope_20,
        )
        if any(value is None for value in required):
            reasons.add("regime_input_missing")
            return None
        if any(value is not None and not value.is_finite() for value in required):
            reasons.add("regime_input_conflicting")
            return None
        return matches[0]

    def _critical_record[Record: EvidenceMetadata](
        self,
        records: Sequence[Record],
        evidence: SupplementalEvidence,
        reasons: set[str],
        lineage: set[str],
    ) -> Record | None:
        lineage.update(record.lineage_id for record in records)
        if not records:
            reasons.add("regime_input_missing")
            return None
        if len(records) != 1:
            reasons.add("regime_input_conflicting")
            return None
        record = records[0]
        if record.observed_at > evidence.as_of:
            reasons.add("regime_input_conflicting")
            return None
        if not record.is_current(evidence.as_of):
            reasons.add("regime_input_stale")
            return None
        return record

    def _broad_trend(
        self, features: FeatureResult | None, reasons: set[str]
    ) -> Decimal:
        if features is None:
            return Decimal()
        close = features.adjusted_close
        sma50 = features.sma_50
        sma200 = features.sma_200
        slope = features.sma_50_slope_20
        if close is None or sma50 is None or sma200 is None or slope is None:
            reasons.add("regime_input_missing")
            return Decimal()
        weight = self._policy.component_weights["broad_trend"]
        if close > sma50 > sma200 and slope > 0:
            return weight
        if close < sma50 < sma200 and slope < 0:
            return -weight
        return Decimal()

    def _breadth(
        self, evidence: BreadthEvidence | None, reasons: set[str]
    ) -> Decimal:
        if evidence is None:
            return Decimal()
        if evidence.total_eligible_issues <= 0:
            reasons.add("regime_input_conflicting")
            return Decimal()
        fraction = Decimal(evidence.issues_above_sma_50) / Decimal(
            evidence.total_eligible_issues
        )
        ratio = self._ratio(
            Decimal(evidence.advancing_issues),
            Decimal(evidence.declining_issues),
            reasons,
            "no_declining_issues",
        )
        weight = self._policy.component_weights["breadth"]
        bullish_ratio = (
            ratio is None and evidence.advancing_issues > 0
        ) or (
            ratio is not None
            and ratio >= self._policy.participation_bullish_ratio
        )
        if (
            fraction >= self._policy.breadth_bullish_above_sma_fraction
            and bullish_ratio
        ):
            return weight
        if (
            fraction <= self._policy.breadth_bearish_above_sma_fraction
            and ratio is not None
            and ratio <= self._policy.participation_bearish_ratio
        ):
            return -weight
        return Decimal()

    def _sector_participation(
        self, evidence: SectorEvidence | None, reasons: set[str]
    ) -> Decimal:
        if evidence is None:
            return Decimal()
        symbols = {item.symbol for item in evidence.observations}
        if len(evidence.observations) != 11 or len(symbols) != 11:
            reasons.add("regime_input_conflicting")
            return Decimal()
        values = tuple(item.close_relative_to_sma_50 for item in evidence.observations)
        returns = tuple(item.return_20_session for item in evidence.observations)
        if any(not value.is_finite() for value in (*values, *returns)):
            reasons.add("regime_input_conflicting")
            return Decimal()
        above = sum(value > 1 for value in values)
        below = sum(value < 1 for value in values)
        weight = self._policy.component_weights["sector_participation"]
        if above >= self._policy.sector_alignment_count:
            return weight
        if below >= self._policy.sector_alignment_count:
            return -weight
        return Decimal()

    def _volume_participation(
        self, evidence: BreadthEvidence | None, reasons: set[str]
    ) -> Decimal:
        if evidence is None:
            return Decimal()
        ratio = self._ratio(
            evidence.up_volume,
            evidence.down_volume,
            reasons,
            "feature_division_by_zero",
        )
        weight = self._policy.component_weights["volume_participation"]
        if ratio is None:
            return weight if evidence.up_volume > 0 else Decimal()
        if ratio >= self._policy.participation_bullish_ratio:
            return weight
        if ratio <= self._policy.participation_bearish_ratio:
            return -weight
        return Decimal()

    def _volatility(
        self, evidence: VolatilityEvidence | None, reasons: set[str]
    ) -> Decimal:
        if evidence is None:
            return Decimal()
        values = (
            evidence.current_value,
            evidence.value_five_sessions_earlier,
            evidence.median_20_session,
        )
        if any(not value.is_finite() or value < 0 for value in values):
            reasons.add("regime_input_conflicting")
            return Decimal()
        prior = evidence.value_five_sessions_earlier
        if prior == 0:
            reasons.add("regime_input_missing")
            return Decimal()
        change = (evidence.current_value - prior) / prior
        expected_direction = VolatilityDirection.FLAT
        if change > 0:
            expected_direction = VolatilityDirection.RISING
        elif change < 0:
            expected_direction = VolatilityDirection.FALLING
        if evidence.direction is not expected_direction:
            reasons.add("regime_input_conflicting")
            return Decimal()
        weight = self._policy.component_weights["volatility_direction"]
        if change <= -self._policy.volatility_change_minimum:
            return weight
        if change >= self._policy.volatility_change_minimum:
            return -weight
        return Decimal()

    def _macro(self, evidence: MacroEvidence | None, reasons: set[str]) -> Decimal:
        if evidence is None:
            return Decimal()
        weight = self._policy.component_weights["macro_overlay"]
        if evidence.state is MacroState.RISK_ON:
            return weight
        if evidence.state is MacroState.RISK_OFF:
            return -weight
        if evidence.state is MacroState.BLOCKED:
            reasons.add("macro_blocked")
        return Decimal()

    def _state(
        self,
        components: dict[str, Decimal],
        signed_score: Decimal,
        sector: SectorEvidence | None,
        reasons: set[str],
    ) -> RegimeState:
        if reasons & _BLOCKING_REASONS:
            return RegimeState.BLOCKED
        trend = components["broad_trend"]
        breadth = components["breadth"]
        if trend * breadth < 0:
            reasons.add("trend_breadth_divergence")
            return RegimeState.MIXED
        if self._has_sector_dispersion(components, sector):
            reasons.add("sector_dispersion")
            return RegimeState.MIXED
        if signed_score >= self._policy.bullish_total_minimum:
            return RegimeState.BULLISH
        if signed_score <= self._policy.bearish_total_maximum:
            return RegimeState.BEARISH
        return RegimeState.NEUTRAL

    def _has_sector_dispersion(
        self, components: dict[str, Decimal], sector: SectorEvidence | None
    ) -> bool:
        if sector is None or components["sector_participation"] != 0:
            return False
        returns = tuple(item.return_20_session for item in sector.observations)
        return any(value > 0 for value in returns) and any(value < 0 for value in returns)

    def _ratio(
        self,
        numerator: Decimal,
        denominator: Decimal,
        reasons: set[str],
        zero_reason: str,
    ) -> Decimal | None:
        if denominator == 0:
            if numerator > 0:
                reasons.add(zero_reason)
            else:
                reasons.add("regime_input_missing")
            return None
        return numerator / denominator
