from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_trader.market_data.models import (
    DataKind,
    DeliverableState,
    ProviderEvent,
    PutCall,
    QualityState,
)
from market_trader.market_data.normalizers import normalize_option_chain


def test_normalizes_complete_standard_chain_and_optional_analytics() -> None:
    result = normalize_option_chain(option_chain_event())

    assert result.rejection is None
    assert result.accepted is not None
    assert result.accepted.underlying == "SPY"
    assert result.accepted.is_complete is True
    assert result.accepted.metadata.quality_state is QualityState.VALID
    contract = result.accepted.contracts[0]
    assert contract.option_type is PutCall.CALL
    assert contract.deliverable is DeliverableState.STANDARD
    assert contract.strike == Decimal("630")
    assert contract.implied_volatility == Decimal("0.21")
    assert contract.delta == Decimal("0.45")


def test_partial_chain_is_degraded_and_explicitly_incomplete() -> None:
    result = normalize_option_chain(option_chain_event(payload_update={"completeness": "partial"}))

    assert result.accepted is not None
    assert result.accepted.metadata.quality_state is QualityState.DEGRADED
    assert result.accepted.metadata.quality_reasons == ("partial_chain",)
    assert result.accepted.is_complete is False


def test_unsupported_deliverable_is_retained_as_degraded_contract() -> None:
    contracts = default_contracts()
    contracts[0]["deliverable"] = "unsupported"

    result = normalize_option_chain(option_chain_event(contracts=contracts))

    assert result.accepted is not None
    assert result.accepted.metadata.quality_state is QualityState.DEGRADED
    assert result.accepted.contracts[0].quality_reasons == ("unsupported_deliverable",)


def test_locked_contract_is_retained_with_quality_reason() -> None:
    contracts = default_contracts()
    contracts[0]["ask"] = contracts[0]["bid"]

    result = normalize_option_chain(option_chain_event(contracts=contracts))

    assert result.accepted is not None
    assert result.accepted.contracts[0].quality_reasons == ("locked_market",)
    assert result.accepted.metadata.quality_state is QualityState.DEGRADED


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("duplicate", "duplicate_contract"),
        ("crossed", "crossed_market"),
        ("expired", "invalid_expiration"),
        ("missing_identity", "missing_contract_identity"),
        ("negative", "negative_value"),
        ("bad_completeness", "invalid_completeness"),
    ],
)
def test_invalid_contract_or_chain_rejects_whole_observation(
    mutation: str,
    reason: str,
) -> None:
    contracts = default_contracts()
    payload_update: dict[str, object] = {}
    if mutation == "duplicate":
        contracts.append(deepcopy(contracts[0]))
    elif mutation == "crossed":
        contracts[0]["ask"] = "1.00"
    elif mutation == "expired":
        contracts[0]["expiration"] = "2026-07-16"
    elif mutation == "missing_identity":
        contracts[0].pop("contract_id")
    elif mutation == "negative":
        contracts[0]["open_interest"] = -1
    else:
        payload_update["completeness"] = "unknown"

    result = normalize_option_chain(
        option_chain_event(contracts=contracts, payload_update=payload_update)
    )

    assert result.accepted is None
    assert result.rejection is not None
    assert reason in result.rejection.reason_codes


def option_chain_event(
    *,
    contracts: list[dict[str, object]] | None = None,
    payload_update: dict[str, object] | None = None,
) -> ProviderEvent:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    payload: dict[str, object] = {
        "underlying": "SPY",
        "session_date": "2026-07-17",
        "completeness": "complete",
        "contracts": contracts if contracts is not None else default_contracts(),
    }
    payload.update(payload_update or {})
    return ProviderEvent(
        source="fixture",
        event_id="chain-1",
        data_kind=DataKind.OPTION_CHAIN,
        observed_at=observed,
        ingested_at=observed,
        payload=payload,
        fixture_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id="corr-1",
    )


def default_contracts() -> list[dict[str, object]]:
    return [
        {
            "contract_id": "SPY-20260821-C-630",
            "expiration": "2026-08-21",
            "strike": "630",
            "option_type": "call",
            "deliverable": "standard",
            "bid": "4.10",
            "ask": "4.20",
            "bid_size": 10,
            "ask_size": 12,
            "last": "4.15",
            "volume": 200,
            "open_interest": 5000,
            "implied_volatility": "0.21",
            "delta": "0.45",
            "gamma": "0.02",
            "theta": "-0.08",
            "vega": "0.15",
        }
    ]
