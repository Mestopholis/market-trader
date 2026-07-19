from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest

from market_trader.catalysts.models import (
    AuthorityClass,
    CatalystDecision,
    CatalystDirection,
    CatalystObservation,
    CatalystPolicyVersions,
    CatalystProviderEvent,
    CitedSummary,
    ConfirmationState,
    EventFamily,
    EventRiskWindow,
    Materiality,
    QuarantinedObservation,
    RiskState,
    SourceFailure,
    SourceFailureKind,
    SourceRunResult,
    SourceState,
    SummarySegment,
)

AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)


def test_public_enums_contain_only_approved_values() -> None:
    assert tuple(EventFamily) == (
        EventFamily.COMPANY_NEWS,
        EventFamily.EARNINGS,
        EventFamily.SEC_FILING,
        EventFamily.ECONOMIC_RELEASE,
        EventFamily.SOCIAL,
    )
    assert tuple(Materiality) == (
        Materiality.MATERIAL,
        Materiality.CONTEXTUAL,
        Materiality.UNKNOWN,
    )
    assert tuple(CatalystDirection) == (
        CatalystDirection.POSITIVE,
        CatalystDirection.NEGATIVE,
        CatalystDirection.NEUTRAL,
        CatalystDirection.UNCLEAR,
    )
    assert tuple(ConfirmationState) == (
        ConfirmationState.CONFIRMED,
        ConfirmationState.UNCONFIRMED,
        ConfirmationState.BLOCKED,
    )
    assert tuple(SourceState) == (
        SourceState.AVAILABLE,
        SourceState.DEGRADED,
        SourceState.STALE,
        SourceState.UNAVAILABLE,
        SourceState.MALFORMED,
    )


def test_policy_versions_use_approved_identifiers() -> None:
    assert CatalystPolicyVersions() == CatalystPolicyVersions(
        source="catalyst-source-policy-v1",
        classification="catalyst-classification-policy-v1",
        risk="event-risk-policy-v1",
        summary="catalyst-summary-policy-v1",
        fixture="catalyst-fixture-v1",
    )


def _event(**updates: object) -> CatalystProviderEvent:
    values: dict[str, object] = {
        "source_id": "recorded-earnings-v1",
        "provider_event_id": "earnings-aapl-2026-q2",
        "event_family": EventFamily.EARNINGS,
        "provider_schema_version": 1,
        "published_at": AS_OF,
        "ingested_at": AS_OF,
        "scheduled_for": None,
        "symbol_identity": "AAPL",
        "structured_fields": {"actual": Decimal("1.25"), "consensus": Decimal("1.20")},
        "external_text": {"headline": "Synthetic earnings result"},
        "source_reference": "fixture://earnings/aapl-2026-q2",
        "correlation_id": "corr-1",
    }
    values.update(updates)
    return CatalystProviderEvent(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field_name",
    ("published_at", "ingested_at", "scheduled_for"),
)
def test_provider_event_rejects_naive_timestamps(field_name: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _event(**{field_name: datetime(2026, 7, 17, 10, 30)})


def test_provider_event_copies_nested_mappings_immutably() -> None:
    tags = ["earnings", "quarterly"]
    structured: dict[str, object] = {"tags": tags, "actual": Decimal("1.25")}
    event = _event(structured_fields=structured)

    tags.append("changed")
    structured["actual"] = Decimal("0")

    assert event.structured_fields["tags"] == ("earnings", "quarterly")
    assert event.structured_fields["actual"] == Decimal("1.25")
    with pytest.raises(TypeError):
        event.structured_fields["actual"] = Decimal("2")  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        event.source_id = "changed"  # type: ignore[misc]


def test_observation_and_decision_sort_reasons_and_lineage() -> None:
    observation = CatalystObservation(
        observation_key="obs-1",
        ingestion_key="ing-1",
        authoritative_digest="a" * 64,
        external_text_digest="b" * 64,
        source_id="recorded-earnings-v1",
        authority_class=AuthorityClass.AUTHORIZED_STRUCTURED,
        event_family=EventFamily.EARNINGS,
        event_category="earnings_result",
        provider_event_id="earnings-1",
        source_reference="fixture://earnings/1",
        symbol="AAPL",
        published_at=AS_OF,
        ingested_at=AS_OF,
        scheduled_for=None,
        valid_until=AS_OF,
        structured_facts={"actual": Decimal("1.25")},
        external_text={"headline": "Synthetic"},
        source_schema_version=1,
        normalization_schema_version=1,
        configuration_version="catalyst-source-policy-v1",
        correlation_id="corr-1",
        quality_reasons=("z_reason", "a_reason", "z_reason"),
    )
    decision = CatalystDecision(
        decision_key="decision-1",
        scope="symbol",
        symbol="AAPL",
        as_of=AS_OF,
        materiality=Materiality.MATERIAL,
        direction=CatalystDirection.POSITIVE,
        confirmation=ConfirmationState.CONFIRMED,
        risk_state=RiskState.CLEAR,
        reasons=("z_reason", "a_reason", "z_reason"),
        observation_keys=("obs-z", "obs-a", "obs-z"),
        policy_versions=CatalystPolicyVersions(),
        input_digest="c" * 64,
        explanation={"lineage": ["z", "a"]},
    )

    assert observation.quality_reasons == ("a_reason", "z_reason")
    assert decision.reasons == ("a_reason", "z_reason")
    assert decision.observation_keys == ("obs-a", "obs-z")
    assert cast(tuple[str, ...], decision.explanation["lineage"]) == ("z", "a")


def test_summary_segments_require_citations_and_are_sorted() -> None:
    segment = SummarySegment(
        text="Synthetic company result exceeded the attributed estimate.",
        observation_keys=("obs-z", "obs-a", "obs-z"),
        source_references=("fixture://z", "fixture://a", "fixture://z"),
    )
    summary = CitedSummary(
        summary_key="summary-1",
        provider_id="recorded-summary-v1",
        generated_at=AS_OF,
        segments=(segment,),
        policy_version="catalyst-summary-policy-v1",
        content_digest="d" * 64,
    )

    assert summary.segments[0].observation_keys == ("obs-a", "obs-z")
    assert summary.segments[0].source_references == ("fixture://a", "fixture://z")
    with pytest.raises(ValueError, match="citation"):
        SummarySegment(text="Uncited", observation_keys=(), source_references=())


def test_outcome_contracts_enforce_aware_times_and_sorted_values() -> None:
    failure = SourceFailure(
        source_id="sec-edgar-public-v1",
        kind=SourceFailureKind.THROTTLED,
        occurred_at=AS_OF,
        reasons=("source_throttled", "source_throttled"),
    )
    quarantine = QuarantinedObservation(
        ingestion_key="ing-1",
        sanitized_payload_digest="e" * 64,
        source_id="fixture",
        provider_event_id="event-1",
        published_at=AS_OF,
        ingested_at=AS_OF,
        reasons=("z", "a"),
        sanitized_payload={"safe": True},
    )
    window = EventRiskWindow(
        category="earnings",
        scope="symbol",
        symbol="AAPL",
        starts_at=AS_OF,
        ends_at=AS_OF,
        state=RiskState.ACTIVE,
        reasons=("earnings_window_active",),
        lineage=("obs-2", "obs-1"),
        policy_version="event-risk-policy-v1",
    )
    result = SourceRunResult(
        run_key="run-1",
        source_id="fixture",
        capability="fixture_replay",
        request_digest="a" * 64,
        source_policy_version="catalyst-source-policy-v1",
        policy_hashes={"sources": "b" * 64},
        as_of=AS_OF,
        state=SourceState.DEGRADED,
        observations=(),
        quarantined=(quarantine,),
        decisions=(),
        summaries=(),
        reasons=("source_partial", "source_partial"),
        result_digest="f" * 64,
    )

    assert failure.reasons == ("source_throttled",)
    assert quarantine.reasons == ("a", "z")
    assert window.lineage == ("obs-1", "obs-2")
    assert result.reasons == ("source_partial",)
