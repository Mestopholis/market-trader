from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_trader.market_data.models import DataKind, ProviderEvent, QualityState
from market_trader.market_data.normalizers import normalize_quote


def test_normalizes_complete_quote_with_exact_values() -> None:
    result = normalize_quote(
        quote_event(
            payload_update={
                "last": "625.15",
                "last_size": 25,
                "last_at": "2026-07-17T14:30:00+00:00",
                "bid_venue": "ARCX",
                "ask_venue": "XNAS",
                "trade_venue": "XNYS",
                "condition_codes": ["R", "T"],
            }
        )
    )

    assert result.rejection is None
    assert result.accepted is not None
    assert result.accepted.symbol == "SPY"
    assert result.accepted.bid == Decimal("625.10")
    assert result.accepted.ask == Decimal("625.20")
    assert result.accepted.last == Decimal("625.15")
    assert result.accepted.condition_codes == ("R", "T")
    assert result.accepted.metadata.quality_state is QualityState.VALID
    assert result.accepted.metadata.normalized_schema_version == 1


def test_locked_quote_is_degraded() -> None:
    result = normalize_quote(quote_event(payload_update={"ask": "625.10"}))

    assert result.accepted is not None
    assert result.accepted.metadata.quality_state is QualityState.DEGRADED
    assert result.accepted.metadata.quality_reasons == ("locked_market",)
    assert result.accepted.bid == Decimal("625.10")


@pytest.mark.parametrize(
    ("payload_update", "reason"),
    [
        ({"ask": "624.99"}, "crossed_market"),
        ({"bid": None}, "missing_top_of_book"),
        ({"ask_size": None}, "missing_top_of_book"),
        ({"bid_size": -1}, "negative_value"),
        ({"bid": "not-a-price"}, "invalid_decimal"),
        ({"bid": 625.1}, "binary_float_not_allowed"),
    ],
)
def test_invalid_quote_is_rejected(payload_update: dict[str, object], reason: str) -> None:
    result = normalize_quote(quote_event(payload_update=payload_update))

    assert result.accepted is None
    assert result.rejection is not None
    assert result.rejection.quality_state is QualityState.QUARANTINED
    assert reason in result.rejection.reason_codes


def test_rejects_wrong_event_kind() -> None:
    event = quote_event()
    wrong_kind = ProviderEvent(
        source=event.source,
        event_id=event.event_id,
        data_kind=DataKind.CANDLE,
        observed_at=event.observed_at,
        ingested_at=event.ingested_at,
        payload=event.payload,
        fixture_schema_version=event.fixture_schema_version,
        configuration_version=event.configuration_version,
        correlation_id=event.correlation_id,
    )

    result = normalize_quote(wrong_kind)

    assert result.rejection is not None
    assert result.rejection.reason_codes == ("unexpected_data_kind",)


def test_rejects_explicit_unknown_payload_schema() -> None:
    result = normalize_quote(quote_event(payload_update={"schema_version": 999}))

    assert result.rejection is not None
    assert result.rejection.reason_codes == ("unknown_payload_schema",)


def quote_event(*, payload_update: dict[str, object] | None = None) -> ProviderEvent:
    payload: dict[str, object] = {
        "symbol": "SPY",
        "bid": "625.10",
        "ask": "625.20",
        "bid_size": 100,
        "ask_size": 200,
    }
    payload.update(payload_update or {})
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
