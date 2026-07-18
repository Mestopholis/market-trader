from datetime import UTC, datetime

import pytest

from market_trader.market_data.models import (
    DataKind,
    ProviderEvent,
    ProviderOperationalState,
    QualityState,
)
from market_trader.market_data.normalizers import normalize_provider_state


@pytest.mark.parametrize(
    "state",
    ["unavailable", "throttled", "partial", "recovering"],
)
def test_provider_failure_and_recovery_states_are_degraded(state: str) -> None:
    result = normalize_provider_state(provider_state_event(state))

    assert result.accepted is not None
    assert result.accepted.state is ProviderOperationalState(state)
    assert result.accepted.metadata.quality_state is QualityState.DEGRADED
    assert result.accepted.metadata.quality_reasons == (f"provider_{state}",)


def test_available_provider_state_is_valid() -> None:
    result = normalize_provider_state(provider_state_event("available"))

    assert result.accepted is not None
    assert result.accepted.metadata.quality_state is QualityState.VALID
    assert result.accepted.metadata.quality_reasons == ()


def test_unknown_provider_state_is_quarantined() -> None:
    result = normalize_provider_state(provider_state_event("mystery"))

    assert result.rejection is not None
    assert result.rejection.reason_codes == ("unknown_provider_state",)


def provider_state_event(state: str) -> ProviderEvent:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    return ProviderEvent(
        source="fixture",
        event_id=f"provider-{state}",
        data_kind=DataKind.PROVIDER_STATE,
        observed_at=observed,
        ingested_at=observed,
        payload={"provider": "fixture", "state": state},
        fixture_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id=f"corr-{state}",
    )
