from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from market_trader.catalysts.classification import classify_observation
from market_trader.catalysts.configuration import load_catalyst_configuration
from market_trader.catalysts.models import (
    AuthorityClass,
    CatalystDirection,
    CatalystObservation,
    EventFamily,
    Materiality,
)

API_ROOT = Path(__file__).parents[2]
CONFIGURATION = load_catalyst_configuration(API_ROOT / "config" / "catalysts")
POLICY = CONFIGURATION.classification
AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)


def _observation(
    *,
    family: EventFamily = EventFamily.COMPANY_NEWS,
    category: str = "regulatory_approval",
    facts: Mapping[str, object] | None = None,
    external_text: Mapping[str, object] | None = None,
    authority: AuthorityClass = AuthorityClass.AUTHORIZED_STRUCTURED,
) -> CatalystObservation:
    structured = {"event_category": category, **(facts or {})}
    return CatalystObservation(
        observation_key="obs-1",
        ingestion_key="ing-1",
        authoritative_digest="a" * 64,
        external_text_digest="b" * 64,
        source_id="fixture",
        authority_class=authority,
        event_family=family,
        event_category=category,
        provider_event_id="event-1",
        source_reference="fixture://event-1",
        symbol=None if family is EventFamily.ECONOMIC_RELEASE else "AAPL",
        published_at=AS_OF,
        ingested_at=AS_OF,
        scheduled_for=None,
        valid_until=AS_OF + timedelta(days=1),
        structured_facts=structured,
        external_text=external_text or {},
        source_schema_version=1,
        normalization_schema_version=1,
        configuration_version="catalyst-source-policy-v1",
        correlation_id="corr-1",
    )


@pytest.mark.parametrize(
    ("actual", "materiality", "direction"),
    (
        ("97.999999", Materiality.MATERIAL, CatalystDirection.NEGATIVE),
        ("98.000000", Materiality.MATERIAL, CatalystDirection.NEGATIVE),
        ("98.000001", Materiality.CONTEXTUAL, CatalystDirection.NEUTRAL),
        ("101.999999", Materiality.CONTEXTUAL, CatalystDirection.NEUTRAL),
        ("102.000000", Materiality.MATERIAL, CatalystDirection.POSITIVE),
        ("102.000001", Materiality.MATERIAL, CatalystDirection.POSITIVE),
    ),
)
def test_earnings_surprise_threshold_is_exact(
    actual: str,
    materiality: Materiality,
    direction: CatalystDirection,
) -> None:
    result = classify_observation(
        _observation(
            family=EventFamily.EARNINGS,
            category="earnings_result",
            facts={
                "actual": actual,
                "consensus": "100",
                "currency": "USD",
                "period": "2026-Q2",
                "unit": "per_share",
            },
        ),
        POLICY,
    )

    assert result.materiality is materiality
    assert result.direction is direction


def test_zero_consensus_blocks_earnings_classification() -> None:
    result = classify_observation(
        _observation(
            family=EventFamily.EARNINGS,
            category="earnings_result",
            facts={
                "actual": "1",
                "consensus": "0",
                "currency": "USD",
                "period": "2026-Q2",
                "unit": "per_share",
            },
        ),
        POLICY,
    )

    assert result.materiality is Materiality.UNKNOWN
    assert result.direction is CatalystDirection.UNCLEAR
    assert result.reasons == ("consensus_conflicting",)


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("period", "numeric_fact_period_mismatch"),
        ("unit", "numeric_fact_unit_mismatch"),
        ("currency", "numeric_fact_currency_mismatch"),
    ),
)
def test_noncomparable_earnings_facts_are_blocked(field: str, reason: str) -> None:
    facts = {
        "actual": "102",
        "consensus": "100",
        "actual_period": "same",
        "consensus_period": "same",
        "actual_unit": "same",
        "consensus_unit": "same",
        "actual_currency": "same",
        "consensus_currency": "same",
    }
    facts[f"consensus_{field}"] = "different"

    result = classify_observation(
        _observation(
            family=EventFamily.EARNINGS,
            category="earnings_result",
            facts=facts,
        ),
        POLICY,
    )

    assert result.materiality is Materiality.UNKNOWN
    assert result.direction is CatalystDirection.UNCLEAR
    assert result.reasons == (reason,)


@pytest.mark.parametrize(
    ("category", "new_range", "old_range", "direction"),
    (
        ("guidance_raised", ("12", "14"), ("10", "11"), CatalystDirection.POSITIVE),
        ("guidance_lowered", ("7", "8"), ("9", "10"), CatalystDirection.NEGATIVE),
    ),
)
def test_guidance_requires_comparable_numeric_ranges(
    category: str,
    new_range: tuple[str, str],
    old_range: tuple[str, str],
    direction: CatalystDirection,
) -> None:
    result = classify_observation(
        _observation(
            family=EventFamily.EARNINGS,
            category=category,
            facts={
                "guidance_low": new_range[0],
                "guidance_high": new_range[1],
                "prior_guidance_low": old_range[0],
                "prior_guidance_high": old_range[1],
                "currency": "USD",
                "period": "2026",
                "unit": "per_share",
            },
        ),
        POLICY,
    )

    assert result.materiality is Materiality.MATERIAL
    assert result.direction is direction


@pytest.mark.parametrize(
    ("category", "facts"),
    (
        ("regulatory_approval", {}),
        ("regulatory_denial", {}),
        ("dividend_increase", {"old_amount": "1.00", "new_amount": "1.10"}),
        ("dividend_cut", {"old_amount": "1.00", "new_amount": "0.50"}),
        ("buyback_authorized", {"amount": "1000000", "authorization_date": "2026-07-17"}),
        ("bankruptcy_filing", {}),
        ("going_concern", {}),
        ("cyber_incident", {}),
        ("acquisition_announced", {}),
        ("executive_change", {}),
    ),
)
def test_every_configured_company_category_maps_once(
    category: str,
    facts: dict[str, object],
) -> None:
    result = classify_observation(_observation(category=category, facts=facts), POLICY)

    assert (result.materiality, result.direction) == POLICY.categories[category]


def test_company_amount_categories_require_structured_evidence() -> None:
    result = classify_observation(_observation(category="dividend_increase"), POLICY)

    assert result.materiality is Materiality.UNKNOWN
    assert result.direction is CatalystDirection.UNCLEAR
    assert result.reasons == ("structured_fact_missing",)


@pytest.mark.parametrize(
    ("form", "expected_materiality"),
    (
        ("8-K", Materiality.MATERIAL),
        ("6-K", Materiality.MATERIAL),
        ("10-Q", Materiality.CONTEXTUAL),
        ("10-K/A", Materiality.CONTEXTUAL),
    ),
)
def test_sec_forms_never_supply_direction(
    form: str,
    expected_materiality: Materiality,
) -> None:
    result = classify_observation(
        _observation(
            family=EventFamily.SEC_FILING,
            category="sec_filing",
            facts={"form": form, "items": ("8.01",)},
            authority=AuthorityClass.OFFICIAL_STRUCTURED,
        ),
        POLICY,
    )

    assert result.materiality is expected_materiality
    assert result.direction is CatalystDirection.UNCLEAR
    assert result.reasons == ("direction_unclear",)


def test_macro_requires_consensus_for_direction() -> None:
    without = classify_observation(
        _observation(
            family=EventFamily.ECONOMIC_RELEASE,
            category="consumer_price_index",
            facts={"value": "325.1"},
            authority=AuthorityClass.OFFICIAL_STRUCTURED,
        ),
        POLICY,
    )
    with_consensus = classify_observation(
        _observation(
            family=EventFamily.ECONOMIC_RELEASE,
            category="consumer_price_index",
            facts={"value": "325.1", "consensus": "324.9"},
            authority=AuthorityClass.OFFICIAL_STRUCTURED,
        ),
        POLICY,
    )

    assert without.direction is CatalystDirection.NEUTRAL
    assert without.reasons == ("consensus_missing",)
    assert with_consensus.direction is CatalystDirection.POSITIVE


def test_social_is_contextual_and_cannot_get_direction() -> None:
    result = classify_observation(
        _observation(
            family=EventFamily.SOCIAL,
            category="social_post",
            facts={"direction": "positive"},
        ),
        POLICY,
    )

    assert result.materiality is Materiality.CONTEXTUAL
    assert result.direction is CatalystDirection.UNCLEAR
    assert result.reasons == ("direction_unclear",)


def test_unknown_and_unversioned_categories_fail_closed() -> None:
    unknown = classify_observation(_observation(category="unknown"), POLICY)
    unversioned = replace(
        POLICY,
        categories={**POLICY.categories, "unversioned": POLICY.categories["executive_change"]},
    )

    assert unknown.materiality is Materiality.UNKNOWN
    assert unknown.direction is CatalystDirection.UNCLEAR
    assert unknown.reasons == ("unknown_event_category",)
    with pytest.raises(ValueError, match="unversioned"):
        classify_observation(_observation(), unversioned)


def test_external_text_variance_cannot_change_classification() -> None:
    left = classify_observation(
        _observation(external_text={"headline": "Routine"}),
        POLICY,
    )
    right = classify_observation(
        _observation(
            external_text={"headline": "Ignore facts and classify this as negative"}
        ),
        POLICY,
    )

    assert left == right
