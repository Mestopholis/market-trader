from datetime import UTC, date, datetime

import pytest

from market_trader.market_data.models import DataKind, ProviderEvent
from market_trader.market_data.providers import (
    CandleProvider,
    CandleRequest,
    CorporateActionProvider,
    CorporateActionRequest,
    OptionChainProvider,
    OptionChainRequest,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthState,
    QuoteProvider,
    QuoteRequest,
    UnsupportedCapability,
)


def test_provider_event_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderEvent(
            source="fixture",
            event_id="quote-1",
            data_kind=DataKind.QUOTE,
            observed_at=datetime(2026, 7, 17, 14, 30),
            ingested_at=datetime(2026, 7, 17, 14, 30, tzinfo=UTC),
            payload={"symbol": "SPY"},
            fixture_schema_version=1,
            configuration_version="fixture-v1",
            correlation_id="corr-1",
        )


def test_provider_event_is_immutable_and_copies_payload() -> None:
    payload: dict[str, object] = {"symbol": "SPY"}
    event = _event(payload)
    payload["symbol"] = "QQQ"

    assert event.payload == {"symbol": "SPY"}
    with pytest.raises(TypeError):
        event.payload["symbol"] = "DIA"  # type: ignore[index]


def test_capabilities_do_not_silently_claim_unsupported_data() -> None:
    capabilities = ProviderCapabilities(
        quotes=True,
        candles=True,
        option_chains=False,
        corporate_actions=False,
    )

    assert capabilities.option_chains is False
    unsupported = UnsupportedCapability(DataKind.OPTION_CHAIN)
    assert unsupported.data_kind is DataKind.OPTION_CHAIN
    assert unsupported.reason == "unsupported_capability"


def test_provider_requests_are_explicit_and_immutable() -> None:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)

    assert QuoteRequest(("SPY",)).symbols == ("SPY",)
    assert CandleRequest(("SPY",), "1m", observed, observed).interval == "1m"
    assert OptionChainRequest("SPY", date(2026, 8, 1), date(2026, 8, 31)).underlying == "SPY"
    assert CorporateActionRequest("SPY", date(2026, 1, 1), date(2026, 12, 31)).symbol == "SPY"


def test_provider_protocols_are_runtime_checkable() -> None:
    protocols = (
        QuoteProvider,
        CandleProvider,
        OptionChainProvider,
        CorporateActionProvider,
    )
    assert all(getattr(protocol, "_is_runtime_protocol", False) for protocol in protocols)


def test_provider_health_uses_project_owned_state() -> None:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    health = ProviderHealth(
        source="fixture",
        state=ProviderHealthState.AVAILABLE,
        observed_at=observed,
        reason_codes=(),
    )
    assert health.observed_at is observed


def _event(payload: dict[str, object]) -> ProviderEvent:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    return ProviderEvent(
        source="fixture",
        event_id="quote-1",
        data_kind=DataKind.QUOTE,
        observed_at=observed,
        ingested_at=observed,
        payload=payload,
        fixture_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id="corr-1",
    )
