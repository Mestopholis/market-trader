from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import median
from zoneinfo import ZoneInfo

from market_trader.market_calendar.models import ExchangeSession
from market_trader.market_data.models import (
    AdjustmentState,
    CandleInterval,
    NormalizedCandle,
    ObservationMetadata,
    QualityState,
)
from market_trader.scanner import (
    FeatureCalculator,
    FeatureResult,
    FiveMinuteBar,
    assign_relative_performance_percentiles,
)
from market_trader.scanner.models import SymbolInput

AS_OF = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)
SESSION = ExchangeSession(
    calendar="XNYS",
    session_date=date(2026, 7, 17),
    market_open=datetime(2026, 7, 17, 13, 30, tzinfo=UTC),
    market_close=datetime(2026, 7, 17, 20, 0, tzinfo=UTC),
    is_early_close=False,
)


def _metadata(event_id: str, session_date: date) -> ObservationMetadata:
    return ObservationMetadata(
        source="fixture",
        event_id=event_id,
        observed_at=AS_OF - timedelta(minutes=1),
        ingested_at=AS_OF - timedelta(seconds=30),
        session_date=session_date,
        normalized_schema_version=1,
        configuration_version="market-data-v1",
        correlation_id="features-test",
        quality_state=QualityState.VALID,
        quality_reasons=(),
    )


def _daily(index: int, close: Decimal | None = None) -> NormalizedCandle:
    day = date(2025, 9, 1) + timedelta(days=index)
    price = close or Decimal(index + 1)
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    return NormalizedCandle(
        symbol="SPY", interval=CandleInterval.DAILY, start=start,
        end=start + timedelta(hours=23), open=price, high=price + 1,
        low=price - 1, close=price, volume=1_000 + index, vwap=price,
        trade_count=100, adjustment=AdjustmentState.ADJUSTED,
        metadata=_metadata(f"daily-{index}", day),
    )


def _minute(index: int, *, volume: int = 100, vwap: Decimal | None = None) -> NormalizedCandle:
    start = SESSION.market_open + timedelta(minutes=index)
    price = Decimal("200") + Decimal(index)
    return NormalizedCandle(
        symbol="SPY", interval=CandleInterval.ONE_MINUTE, start=start,
        end=start + timedelta(minutes=1), open=price, high=price + 1,
        low=price - 1, close=price + Decimal("0.5"), volume=volume,
        vwap=price if vwap is None else vwap, trade_count=10,
        adjustment=AdjustmentState.ADJUSTED,
        metadata=_metadata(f"minute-{index}", SESSION.session_date),
    )


def _historical_minutes(
    session_date: date, *, cumulative_minutes: int = 10, volume: int = 50
) -> tuple[NormalizedCandle, ...]:
    eastern = ZoneInfo("America/New_York")
    local_open = datetime.combine(
        session_date, datetime.min.time().replace(hour=9, minute=30), tzinfo=eastern
    )
    market_open = local_open.astimezone(UTC)
    return tuple(
        replace(
            _minute(index, volume=volume),
            start=market_open + timedelta(minutes=index),
            end=market_open + timedelta(minutes=index + 1),
            metadata=_metadata(f"historical-{session_date}-{index}", session_date),
        )
        for index in range(cumulative_minutes)
    )


def test_calculates_daily_and_session_features_with_complete_windows() -> None:
    result = FeatureCalculator().calculate(
        SymbolInput(
            symbol="SPY",
            daily_candles=tuple(_daily(index) for index in range(220)),
            intraday_candles=tuple(_minute(index) for index in range(10)),
        ),
        as_of=AS_OF,
        session=SESSION,
    )

    assert result.adjusted_close == Decimal("220")
    assert result.daily_session_count == 220
    assert result.sma_20 == Decimal("210.5")
    assert result.sma_50 == Decimal("195.5")
    assert result.sma_200 == Decimal("120.5")
    assert result.sma_50_slope_20 == (Decimal("195.5") - Decimal("175.5")) / Decimal("175.5")
    assert result.prior_20_high == Decimal("221")
    assert result.prior_20_low == Decimal("200")
    expected_dollar_volumes = [
        Decimal(index + 1) * (1_000 + index) for index in range(200, 220)
    ]
    assert result.median_dollar_volume_20 == median(expected_dollar_volumes)
    assert result.session_open == Decimal("200")
    assert result.session_high == Decimal("210")
    assert result.session_low == Decimal("199")
    assert result.session_close == Decimal("209.5")
    assert result.session_volume == 1_000
    assert result.session_vwap == Decimal("204.5")
    assert len(result.five_minute_bars) == 2


def test_excludes_future_and_partial_five_minute_bars() -> None:
    future = replace(_minute(6), end=AS_OF + timedelta(minutes=1))
    result = FeatureCalculator().calculate(
        SymbolInput(symbol="SPY", daily_candles=tuple(_daily(i) for i in range(200)),
                    intraday_candles=tuple([*(_minute(i) for i in range(6)), future])),
        as_of=AS_OF,
        session=SESSION,
    )
    assert result.session_volume == 600
    assert len(result.five_minute_bars) == 1


def test_missing_vwap_zero_volume_and_insufficient_history_return_stable_reasons() -> None:
    candle = replace(_minute(0), volume=0, vwap=None)
    result = FeatureCalculator().calculate(
        SymbolInput(symbol="SPY", daily_candles=tuple(_daily(i) for i in range(19)),
                    intraday_candles=(candle,)),
        as_of=AS_OF,
        session=SESSION,
    )
    assert result.session_vwap is None
    assert "feature_division_by_zero" in result.reasons
    assert "feature_input_missing" in result.reasons


def test_positive_volume_without_minute_vwap_returns_stable_reason() -> None:
    result = FeatureCalculator().calculate(
        SymbolInput(symbol="SPY", intraday_candles=(replace(_minute(0), vwap=None),)),
        as_of=AS_OF,
        session=SESSION,
    )

    assert result.session_vwap is None
    assert "missing_session_vwap" in result.reasons


def test_percentiles_use_minimum_rank_for_ties_and_ignore_blocked_features() -> None:
    calculator = FeatureCalculator()
    base = calculator.calculate(
        SymbolInput(symbol="A", daily_candles=tuple(_daily(i) for i in range(220))),
        as_of=AS_OF, session=SESSION,
    )
    values = (
        replace(base, symbol="C", return_20=Decimal("0.30")),
        replace(base, symbol="A", return_20=Decimal("0.10")),
        replace(base, symbol="B", return_20=Decimal("0.10")),
        replace(base, symbol="D", return_20=None),
    )
    ranked = assign_relative_performance_percentiles(values)
    assert {item.symbol: item.relative_strength_percentile_20 for item in ranked} == {
        "A": Decimal("0"), "B": Decimal("0"), "C": Decimal("100"), "D": None,
    }


def test_relative_volume_uses_twenty_sessions_at_same_local_minute_offset() -> None:
    historical_dates = tuple(date(2026, 2, 16) + timedelta(days=index) for index in range(20))
    historical = tuple(
        candle
        for session_date in historical_dates
        for candle in _historical_minutes(session_date)
    )
    current = tuple(_minute(index, volume=100) for index in range(10))

    result = FeatureCalculator().calculate(
        SymbolInput(
            symbol="SPY",
            daily_candles=tuple(_daily(index) for index in range(220)),
            intraday_candles=tuple(reversed((*historical, *current))),
        ),
        as_of=AS_OF,
        session=SESSION,
    )

    assert result.relative_volume_20 == Decimal("2")
    assert "feature_input_missing" not in result.reasons


def test_relative_volume_zero_baseline_returns_stable_reason() -> None:
    historical = tuple(
        candle
        for index in range(20)
        for candle in _historical_minutes(
            date(2026, 2, 16) + timedelta(days=index), volume=0
        )
    )
    result = FeatureCalculator().calculate(
        SymbolInput(
            symbol="SPY",
            daily_candles=tuple(_daily(index) for index in range(220)),
            intraday_candles=(*historical, *(_minute(index) for index in range(10))),
        ),
        as_of=AS_OF,
        session=SESSION,
    )

    assert result.relative_volume_20 is None
    assert "feature_division_by_zero" in result.reasons


def test_duplicate_gap_and_unadjusted_candles_return_stable_reasons() -> None:
    duplicate = replace(_minute(0), metadata=_metadata("duplicate", SESSION.session_date))
    unadjusted = replace(_daily(219), adjustment=AdjustmentState.UNADJUSTED)
    result = FeatureCalculator().calculate(
        SymbolInput(
            symbol="SPY",
            daily_candles=(*(_daily(index) for index in range(219)), unadjusted),
            intraday_candles=(_minute(0), duplicate, _minute(2)),
        ),
        as_of=AS_OF,
        session=SESSION,
    )

    assert "feature_input_conflicting" in result.reasons
    assert "feature_input_missing" in result.reasons


def test_nonfinite_or_inconsistent_ohlc_is_not_used() -> None:
    nonfinite = replace(_daily(219), close=Decimal("NaN"))
    inconsistent = replace(_minute(0), high=Decimal("199"))
    result = FeatureCalculator().calculate(
        SymbolInput(
            symbol="SPY",
            daily_candles=(*(_daily(index) for index in range(219)), nonfinite),
            intraday_candles=(inconsistent,),
        ),
        as_of=AS_OF,
        session=SESSION,
    )

    assert result.adjusted_close == Decimal("219")
    assert result.session_open is None
    assert "feature_nonfinite" in result.reasons
    assert "feature_input_conflicting" in result.reasons


def test_early_close_excludes_at_close_candle_and_partial_bucket() -> None:
    early_session = replace(
        SESSION,
        market_close=SESSION.market_open + timedelta(minutes=8),
        is_early_close=True,
    )
    candles = tuple(_minute(index) for index in range(9))
    result = FeatureCalculator().calculate(
        SymbolInput(symbol="SPY", intraday_candles=candles),
        as_of=AS_OF,
        session=early_session,
    )

    assert result.session_volume == 800
    assert len(result.five_minute_bars) == 1


def test_observations_recorded_after_as_of_are_excluded() -> None:
    future_metadata = replace(
        _metadata("future-observation", date(2026, 4, 8)),
        observed_at=AS_OF + timedelta(seconds=1),
        ingested_at=AS_OF + timedelta(seconds=2),
    )
    future_observation = replace(_daily(219), metadata=future_metadata)

    result = FeatureCalculator().calculate(
        SymbolInput(
            symbol="SPY",
            daily_candles=(*(_daily(index) for index in range(219)), future_observation),
        ),
        as_of=AS_OF,
        session=SESSION,
    )

    assert result.adjusted_close == Decimal("219")
    assert result.daily_session_count == 219


def test_calculation_is_independent_of_input_order() -> None:
    daily = tuple(_daily(index) for index in range(220))
    intraday = tuple(_minute(index) for index in range(10))
    calculator = FeatureCalculator()

    ordered = calculator.calculate(
        SymbolInput(symbol="SPY", daily_candles=daily, intraday_candles=intraday),
        as_of=AS_OF,
        session=SESSION,
    )
    reversed_result = calculator.calculate(
        SymbolInput(
            symbol="SPY",
            daily_candles=tuple(reversed(daily)),
            intraday_candles=tuple(reversed(intraday)),
        ),
        as_of=AS_OF,
        session=SESSION,
    )

    assert reversed_result == ordered


def test_feature_contracts_are_public() -> None:
    assert FeatureCalculator.version == "scanner-features-v1"
    assert FeatureResult.__module__ == "market_trader.scanner.features"
    assert FiveMinuteBar.__module__ == "market_trader.scanner.features"
