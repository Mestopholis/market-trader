from dataclasses import dataclass

from market_trader.market_data.models import ProviderOperationalState, QualityState
from market_trader.scanner.configuration import EligibilityPolicy, UniverseEntry
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import EligibilityResult, EligibilityStatus


@dataclass(frozen=True)
class EligibilityQuality:
    repository_symbol: str | None
    symbol_active: bool | None
    daily_quality_state: QualityState | None
    provider_state: ProviderOperationalState | None
    halted: bool | None
    quote_updating: bool | None
    adjustment_supported: bool | None
    corporate_actions_resolved: bool | None
    conflicting_input: bool = False


class EligibilityEvaluator:
    def __init__(self, policy: EligibilityPolicy) -> None:
        self._policy = policy
        self.version = policy.version

    def evaluate(
        self,
        member: UniverseEntry | None,
        features: FeatureResult,
        quality: EligibilityQuality,
    ) -> EligibilityResult:
        if member is None:
            return EligibilityResult(
                symbol=features.symbol,
                status=EligibilityStatus.INELIGIBLE,
                policy_version=self.version,
                reasons=("not_in_universe",),
            )

        observed = {
            "adjusted_close": features.adjusted_close,
            "completed_daily_sessions": features.daily_session_count,
            "median_dollar_volume_20": features.median_dollar_volume_20,
            "security_type": member.security_type,
        }
        blockers = self._blocking_reasons(member, features, quality)
        if blockers:
            return EligibilityResult(
                symbol=member.display_symbol,
                status=EligibilityStatus.BLOCKED,
                policy_version=self.version,
                reasons=tuple(sorted(blockers)),
                observed=observed,
            )

        failures = self._ineligibility_reasons(member, features, quality)
        return EligibilityResult(
            symbol=member.display_symbol,
            status=(
                EligibilityStatus.INELIGIBLE
                if failures
                else EligibilityStatus.ELIGIBLE
            ),
            policy_version=self.version,
            reasons=tuple(sorted(failures)),
            observed=observed,
        )

    def _blocking_reasons(
        self,
        member: UniverseEntry,
        features: FeatureResult,
        quality: EligibilityQuality,
    ) -> set[str]:
        reasons: set[str] = set()
        required_quality = (
            quality.repository_symbol,
            quality.symbol_active,
            quality.daily_quality_state,
            quality.provider_state,
            quality.halted,
            quality.quote_updating,
            quality.adjustment_supported,
            quality.corporate_actions_resolved,
        )
        if any(value is None for value in required_quality):
            reasons.add("missing_required_input")
        if features.adjusted_close is None or features.median_dollar_volume_20 is None:
            reasons.add("missing_required_input")
        if quality.conflicting_input:
            reasons.add("conflicting_input")
        if features.symbol != member.display_symbol:
            reasons.add("conflicting_input")
        feature_decimals = (
            features.adjusted_close,
            features.median_dollar_volume_20,
        )
        if any(value is not None and not value.is_finite() for value in feature_decimals):
            reasons.add("conflicting_input")
        if (
            quality.repository_symbol is not None
            and quality.repository_symbol != member.display_symbol
        ):
            reasons.add("conflicting_input")
        if quality.daily_quality_state is QualityState.STALE:
            reasons.add("stale_market_data")
        elif (
            quality.daily_quality_state is not None
            and quality.daily_quality_state.value
            not in self._policy.permitted_quality_states
        ):
            reasons.add("conflicting_input")
        if (
            self._policy.provider_unavailable_blocks
            and quality.provider_state is ProviderOperationalState.UNAVAILABLE
        ):
            reasons.add("provider_unavailable")
        if self._policy.halt_blocks and quality.halted is True:
            reasons.add("halted_symbol")
        if self._policy.non_updating_quote_blocks and quality.quote_updating is False:
            reasons.add("non_updating_quote")
        if (
            self._policy.unsupported_adjustment_blocks
            and quality.adjustment_supported is False
        ):
            reasons.add("unsupported_adjustment")
        if (
            self._policy.unresolved_corporate_action_blocks
            and quality.corporate_actions_resolved is False
        ):
            reasons.add("unresolved_corporate_action")
        return reasons

    def _ineligibility_reasons(
        self,
        member: UniverseEntry,
        features: FeatureResult,
        quality: EligibilityQuality,
    ) -> set[str]:
        reasons: set[str] = set()
        if quality.symbol_active is False:
            reasons.add("inactive_symbol")
        if member.security_type not in self._policy.allowed_security_types:
            reasons.add("security_type_ineligible")

        adjusted_close = features.adjusted_close
        median_dollar_volume = features.median_dollar_volume_20
        if adjusted_close is not None:
            below = adjusted_close < self._policy.minimum_adjusted_close
            above = adjusted_close > self._policy.maximum_adjusted_close
            if not self._policy.price_bounds_inclusive:
                below = adjusted_close <= self._policy.minimum_adjusted_close
                above = adjusted_close >= self._policy.maximum_adjusted_close
            if below:
                reasons.add("price_below_minimum")
            if above:
                reasons.add("price_above_maximum")
        if features.daily_session_count < self._policy.minimum_completed_daily_sessions:
            reasons.add("insufficient_daily_history")
        if median_dollar_volume is not None:
            below_volume = median_dollar_volume < self._policy.minimum_median_dollar_volume
            if not self._policy.dollar_volume_minimum_inclusive:
                below_volume = (
                    median_dollar_volume <= self._policy.minimum_median_dollar_volume
                )
            if below_volume:
                reasons.add("dollar_volume_below_minimum")
        return reasons
