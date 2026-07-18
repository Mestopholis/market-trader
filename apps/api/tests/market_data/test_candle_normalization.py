from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from market_trader.market_data.models import (
    AdjustmentState,
    CandleInterval,
    DataKind,
    ProviderEvent,
)
from market_trader.market_data.normalizers import normalize_candle


def test_normalizes_completed_one_minute_candle() -> None:
    result = normalize_candle(candle_event())

    assert result.rejection is None
    assert result.accepted is not None
    assert result.accepted.interval is CandleInterval.ONE_MINUTE
    assert result.accepted.adjustment is AdjustmentState.UNADJUSTED
    assert result.accepted.open == Decimal("625.00")
    assert result.accepted.vwap == Decimal("625.08")
    assert result.accepted.trade_count == 42
    assert result.accepted.end - result.accepted.start == timedelta(minutes=1)
    assert result.accepted.metadata.session_date == date(2026, 7, 17)


def test_normalizes_daily_candle_with_explicit_session() -> None:
    start = datetime(2026, 7, 17, 13, 30, tzinfo=UTC)
    end = datetime(2026, 7, 17, 20, 0, tzinfo=UTC)
    result = normalize_candle(
        candle_event(
            interval="1d",
            start=start,
            end=end,
            ingested_at=end,
            payload_update={"adjustment": "adjusted"},
        )
    )

    assert result.accepted is not None
    assert result.accepted.interval is CandleInterval.DAILY
    assert result.accepted.adjustment is AdjustmentState.ADJUSTED
    assert result.accepted.start == start
    assert result.accepted.end == end


@pytest.mark.parametrize(
    ("payload_update", "reason"),
    [
        ({"high": "624.00"}, "inconsistent_ohlc"),
        ({"low": "626.00"}, "inconsistent_ohlc"),
        ({"volume": -1}, "negative_value"),
        ({"trade_count": -1}, "negative_value"),
        ({"start": "2026-07-17T14:31:00+00:00"}, "invalid_time_range"),
        ({"interval": "5m"}, "unsupported_interval"),
        ({"adjustment": "unknown"}, "invalid_adjustment_state"),
    ],
)
def test_rejects_invalid_candle(payload_update: dict[str, object], reason: str) -> None:
    result = normalize_candle(candle_event(payload_update=payload_update))

    assert result.rejection is not None
    assert reason in result.rejection.reason_codes


def test_rejects_one_minute_candle_with_wrong_duration() -> None:
    result = normalize_candle(
        candle_event(end=datetime(2026, 7, 17, 14, 32, tzinfo=UTC))
    )

    assert result.rejection is not None
    assert result.rejection.reason_codes == ("invalid_interval_duration",)


def test_accepts_bar_end_exactly_five_seconds_ahead_of_ingestion() -> None:
    end = datetime(2026, 7, 17, 14, 31, tzinfo=UTC)
    result = normalize_candle(candle_event(end=end, ingested_at=end - timedelta(seconds=5)))

    assert result.accepted is not None


def test_rejects_bar_end_beyond_future_tolerance() -> None:
    end = datetime(2026, 7, 17, 14, 31, tzinfo=UTC)
    result = normalize_candle(
        candle_event(end=end, ingested_at=end - timedelta(seconds=5, microseconds=1))
    )

    assert result.rejection is not None
    assert result.rejection.reason_codes == ("future_timestamp",)


def candle_event(
    *,
    interval: str = "1m",
    start: datetime | None = None,
    end: datetime | None = None,
    ingested_at: datetime | None = None,
    payload_update: dict[str, object] | None = None,
) -> ProviderEvent:
    start = start or datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    end = end or start + timedelta(minutes=1)
    payload: dict[str, object] = {
        "symbol": "SPY",
        "interval": interval,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "open": "625.00",
        "high": "625.20",
        "low": "624.95",
        "close": "625.10",
        "volume": 1000,
        "vwap": "625.08",
        "trade_count": 42,
        "adjustment": "unadjusted",
        "session_date": "2026-07-17",
    }
    payload.update(payload_update or {})
    return ProviderEvent(
        source="fixture",
        event_id="candle-1",
        data_kind=DataKind.CANDLE,
        observed_at=end,
        ingested_at=ingested_at or end,
        payload=payload,
        fixture_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id="corr-1",
    )
