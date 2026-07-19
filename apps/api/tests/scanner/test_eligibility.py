from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from market_trader.market_data.models import ProviderOperationalState, QualityState
from market_trader.scanner import EligibilityEvaluator, EligibilityQuality
from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import EligibilityStatus

CONFIGURATION_PATH = Path(__file__).parents[2] / "config" / "scanner"
CONFIGURATION = load_scanner_configuration(CONFIGURATION_PATH)
POLICY = CONFIGURATION.eligibility
MEMBER = next(
    entry for entry in CONFIGURATION.universe.entries if entry.display_symbol == "AAPL"
)


def _features(
    *,
    adjusted_close: Decimal | None = Decimal("100"),
    daily_session_count: int = 200,
    median_dollar_volume_20: Decimal | None = Decimal("25000000"),
) -> FeatureResult:
    return FeatureResult(
        symbol="AAPL",
        adjusted_close=adjusted_close,
        daily_session_count=daily_session_count,
        median_dollar_volume_20=median_dollar_volume_20,
    )


def _quality(**changes: object) -> EligibilityQuality:
    values: dict[str, object] = {
        "repository_symbol": "AAPL",
        "symbol_active": True,
        "daily_quality_state": QualityState.VALID,
        "provider_state": ProviderOperationalState.AVAILABLE,
        "halted": False,
        "quote_updating": True,
        "adjustment_supported": True,
        "corporate_actions_resolved": True,
        "conflicting_input": False,
    }
    values.update(changes)
    return EligibilityQuality(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("price", [Decimal("10.00"), Decimal("1000.00")])
def test_inclusive_price_boundaries_are_eligible(price: Decimal) -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        _features(adjusted_close=price),
        _quality(),
    )

    assert result.status is EligibilityStatus.ELIGIBLE
    assert result.reasons == ()
    assert result.policy_version == "eligibility-policy-v1"


@pytest.mark.parametrize(
    ("features", "reason"),
    [
        (_features(adjusted_close=Decimal("9.99")), "price_below_minimum"),
        (_features(adjusted_close=Decimal("1000.01")), "price_above_maximum"),
        (_features(daily_session_count=199), "insufficient_daily_history"),
        (
            _features(median_dollar_volume_20=Decimal("24999999.99")),
            "dollar_volume_below_minimum",
        ),
    ],
)
def test_complete_evidence_below_threshold_is_ineligible(
    features: FeatureResult, reason: str
) -> None:
    result = EligibilityEvaluator(POLICY).evaluate(MEMBER, features, _quality())

    assert result.status is EligibilityStatus.INELIGIBLE
    assert result.reasons == (reason,)


@pytest.mark.parametrize("security_type", ["common_stock", "unleveraged_etf"])
def test_allowed_security_types_are_eligible(security_type: str) -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        replace(MEMBER, security_type=security_type),
        _features(),
        _quality(),
    )

    assert result.status is EligibilityStatus.ELIGIBLE


def test_degraded_daily_data_and_partial_provider_are_not_unavailable() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        _features(),
        _quality(
            daily_quality_state=QualityState.DEGRADED,
            provider_state=ProviderOperationalState.PARTIAL,
        ),
    )

    assert result.status is EligibilityStatus.ELIGIBLE


def test_unsupported_security_type_and_inactive_symbol_are_ineligible() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        replace(MEMBER, security_type="leveraged_etf"),
        _features(),
        _quality(symbol_active=False),
    )

    assert result.status is EligibilityStatus.INELIGIBLE
    assert result.reasons == ("inactive_symbol", "security_type_ineligible")


def test_symbol_outside_universe_is_ineligible() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(None, _features(), _quality())

    assert result.status is EligibilityStatus.INELIGIBLE
    assert result.reasons == ("not_in_universe",)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"daily_quality_state": QualityState.STALE}, "stale_market_data"),
        (
            {"provider_state": ProviderOperationalState.UNAVAILABLE},
            "provider_unavailable",
        ),
        ({"halted": True}, "halted_symbol"),
        ({"quote_updating": False}, "non_updating_quote"),
        ({"adjustment_supported": False}, "unsupported_adjustment"),
        ({"corporate_actions_resolved": False}, "unresolved_corporate_action"),
    ],
)
def test_complete_blocking_evidence_blocks(
    changes: dict[str, object], reason: str
) -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        _features(),
        _quality(**changes),
    )

    assert result.status is EligibilityStatus.BLOCKED
    assert result.reasons == (reason,)


@pytest.mark.parametrize(
    "changes",
    [
        {"repository_symbol": None},
        {"symbol_active": None},
        {"daily_quality_state": None},
        {"provider_state": None},
        {"halted": None},
        {"quote_updating": None},
        {"adjustment_supported": None},
        {"corporate_actions_resolved": None},
    ],
)
def test_missing_required_quality_evidence_blocks(changes: dict[str, object]) -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        _features(),
        _quality(**changes),
    )

    assert result.status is EligibilityStatus.BLOCKED
    assert result.reasons == ("missing_required_input",)


def test_missing_feature_values_block_instead_of_becoming_zero() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        _features(adjusted_close=None, median_dollar_volume_20=None),
        _quality(),
    )

    assert result.status is EligibilityStatus.BLOCKED
    assert result.reasons == ("missing_required_input",)


@pytest.mark.parametrize(
    "quality",
    [
        _quality(repository_symbol="MSFT"),
        _quality(daily_quality_state=QualityState.QUARANTINED),
        _quality(conflicting_input=True),
    ],
)
def test_conflicting_evidence_blocks(quality: EligibilityQuality) -> None:
    result = EligibilityEvaluator(POLICY).evaluate(MEMBER, _features(), quality)

    assert result.status is EligibilityStatus.BLOCKED
    assert result.reasons == ("conflicting_input",)


def test_nonfinite_feature_value_blocks_as_conflicting() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        _features(adjusted_close=Decimal("NaN")),
        _quality(),
    )

    assert result.status is EligibilityStatus.BLOCKED
    assert result.reasons == ("conflicting_input",)


def test_feature_symbol_mismatch_blocks_as_conflicting() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        replace(_features(), symbol="MSFT"),
        _quality(),
    )

    assert result.status is EligibilityStatus.BLOCKED
    assert result.reasons == ("conflicting_input",)


def test_blockers_take_precedence_and_multiple_reasons_are_sorted() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(
        MEMBER,
        _features(adjusted_close=Decimal("9")),
        _quality(
            halted=True,
            provider_state=ProviderOperationalState.UNAVAILABLE,
            quote_updating=False,
        ),
    )

    assert result.status is EligibilityStatus.BLOCKED
    assert result.reasons == (
        "halted_symbol",
        "non_updating_quote",
        "provider_unavailable",
    )


def test_observed_values_are_bounded_to_decision_inputs() -> None:
    result = EligibilityEvaluator(POLICY).evaluate(MEMBER, _features(), _quality())

    assert dict(result.observed) == {
        "adjusted_close": Decimal("100"),
        "completed_daily_sessions": 200,
        "median_dollar_volume_20": Decimal("25000000"),
        "security_type": "common_stock",
    }
