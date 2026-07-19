from collections import defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from zoneinfo import ZoneInfo

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.models import ExchangeSession
from market_trader.market_data.models import (
    AdjustmentState,
    CandleInterval,
    NormalizedCandle,
)
from market_trader.scanner.models import SymbolInput

_XNYS_TIMEZONE = ZoneInfo("America/New_York")
_XNYS_OPEN = time(hour=9, minute=30)
_ONE_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class FiveMinuteBar:
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class FeatureResult:
    symbol: str
    adjusted_close: Decimal | None = None
    daily_session_count: int = 0
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    sma_200: Decimal | None = None
    sma_50_slope_20: Decimal | None = None
    prior_20_high: Decimal | None = None
    prior_20_low: Decimal | None = None
    median_dollar_volume_20: Decimal | None = None
    session_open: Decimal | None = None
    session_high: Decimal | None = None
    session_low: Decimal | None = None
    session_close: Decimal | None = None
    session_volume: int = 0
    session_vwap: Decimal | None = None
    relative_volume_20: Decimal | None = None
    return_20: Decimal | None = None
    relative_strength_percentile_20: Decimal | None = None
    five_minute_bars: tuple[FiveMinuteBar, ...] = ()
    reasons: tuple[str, ...] = ()


class FeatureCalculator:
    version = "scanner-features-v1"

    def calculate(
        self,
        symbol: SymbolInput,
        *,
        as_of: datetime,
        session: ExchangeSession,
    ) -> FeatureResult:
        reference = ensure_utc(as_of)
        reasons: set[str] = set()
        daily = _daily_candles(symbol, reference, session, reasons)
        intraday = _intraday_candles(symbol, reference, session, reasons)
        current = tuple(
            candle
            for candle in intraday
            if candle.metadata.session_date == session.session_date
            and session.market_open <= candle.start
            and candle.end <= session.market_close
        )
        _flag_current_session_gaps(current, session, reasons)

        closes = tuple(candle.close for candle in daily)
        sma20 = _mean(closes, 20, reasons)
        sma50 = _mean(closes, 50, reasons)
        sma200 = _mean(closes, 200, reasons)
        slope = _sma_50_slope_20(closes, sma50, reasons)
        prior = daily[-20:] if len(daily) >= 20 else ()
        if not prior:
            reasons.add("feature_input_missing")

        session_volume = sum(candle.volume for candle in current)
        session_vwap = _session_vwap(current, session_volume, reasons)
        relative_volume = _relative_volume_20(
            current, intraday, session, session_volume, reasons
        )

        return FeatureResult(
            symbol=symbol.symbol,
            adjusted_close=closes[-1] if closes else None,
            daily_session_count=len(daily),
            sma_20=sma20,
            sma_50=sma50,
            sma_200=sma200,
            sma_50_slope_20=slope,
            prior_20_high=max((candle.high for candle in prior), default=None),
            prior_20_low=min((candle.low for candle in prior), default=None),
            median_dollar_volume_20=_median_dollar_volume(prior),
            session_open=current[0].open if current else None,
            session_high=max((candle.high for candle in current), default=None),
            session_low=min((candle.low for candle in current), default=None),
            session_close=current[-1].close if current else None,
            session_volume=session_volume,
            session_vwap=session_vwap,
            relative_volume_20=relative_volume,
            return_20=_return_20(closes, reasons),
            five_minute_bars=_five_minute_bars(current, session),
            reasons=tuple(sorted(reasons)),
        )


def _daily_candles(
    symbol: SymbolInput,
    reference: datetime,
    session: ExchangeSession,
    reasons: set[str],
) -> tuple[NormalizedCandle, ...]:
    candidates = tuple(
        candle
        for candle in symbol.daily_candles
        if candle.end <= reference
        and candle.metadata.observed_at <= reference
        and candle.metadata.ingested_at <= reference
        and candle.metadata.session_date is not None
        and candle.metadata.session_date < session.session_date
    )
    return _validated_unique_candles(
        candidates,
        symbol=symbol.symbol,
        interval=CandleInterval.DAILY,
        identity=lambda candle: candle.metadata.session_date,
        reasons=reasons,
    )


def _intraday_candles(
    symbol: SymbolInput,
    reference: datetime,
    session: ExchangeSession,
    reasons: set[str],
) -> tuple[NormalizedCandle, ...]:
    candidates = tuple(
        candle
        for candle in symbol.intraday_candles
        if candle.end <= reference
        and candle.metadata.observed_at <= reference
        and candle.metadata.ingested_at <= reference
        and candle.metadata.session_date is not None
        and candle.metadata.session_date <= session.session_date
    )
    return _validated_unique_candles(
        candidates,
        symbol=symbol.symbol,
        interval=CandleInterval.ONE_MINUTE,
        identity=lambda candle: (candle.metadata.session_date, candle.start),
        reasons=reasons,
    )


def _validated_unique_candles(
    candles: Sequence[NormalizedCandle],
    *,
    symbol: str,
    interval: CandleInterval,
    identity: Callable[[NormalizedCandle], Hashable],
    reasons: set[str],
) -> tuple[NormalizedCandle, ...]:
    grouped: dict[Hashable, list[NormalizedCandle]] = defaultdict(list)
    for candle in candles:
        grouped[identity(candle)].append(candle)

    valid: list[NormalizedCandle] = []
    for key in sorted(grouped, key=str):
        group = grouped[key]
        if len(group) != 1:
            reasons.add("feature_input_conflicting")
            continue
        candle = group[0]
        if candle.symbol != symbol or candle.interval is not interval:
            reasons.add("feature_input_conflicting")
            continue
        if candle.adjustment is not AdjustmentState.ADJUSTED:
            reasons.add("feature_input_conflicting")
            continue
        if not _has_finite_values(candle):
            reasons.add("feature_nonfinite")
            continue
        if not _has_valid_shape(candle, interval):
            reasons.add("feature_input_conflicting")
            continue
        valid.append(candle)
    return tuple(sorted(valid, key=lambda candle: (candle.start, candle.end)))


def _has_finite_values(candle: NormalizedCandle) -> bool:
    values = (candle.open, candle.high, candle.low, candle.close)
    return all(value.is_finite() for value in values) and (
        candle.vwap is None or candle.vwap.is_finite()
    )


def _has_valid_shape(candle: NormalizedCandle, interval: CandleInterval) -> bool:
    if candle.volume < 0 or candle.end <= candle.start:
        return False
    if interval is CandleInterval.ONE_MINUTE and candle.end - candle.start != _ONE_MINUTE:
        return False
    return (
        candle.low <= candle.open <= candle.high
        and candle.low <= candle.close <= candle.high
    )


def _mean(
    values: Sequence[Decimal], window: int, reasons: set[str]
) -> Decimal | None:
    if len(values) < window:
        reasons.add("feature_input_missing")
        return None
    return sum(values[-window:], Decimal()) / Decimal(window)


def _sma_50_slope_20(
    closes: Sequence[Decimal], current: Decimal | None, reasons: set[str]
) -> Decimal | None:
    if len(closes) < 70 or current is None:
        reasons.add("feature_input_missing")
        return None
    earlier = sum(closes[-70:-20], Decimal()) / Decimal(50)
    if earlier == 0:
        reasons.add("feature_division_by_zero")
        return None
    return (current - earlier) / earlier


def _median_dollar_volume(candles: Sequence[NormalizedCandle]) -> Decimal | None:
    if len(candles) != 20:
        return None
    return median(candle.close * candle.volume for candle in candles)


def _session_vwap(
    candles: Sequence[NormalizedCandle], volume: int, reasons: set[str]
) -> Decimal | None:
    if not candles:
        return None
    if volume == 0:
        reasons.add("feature_division_by_zero")
        return None
    if any(candle.vwap is None for candle in candles):
        reasons.add("missing_session_vwap")
        return None
    weighted = sum(
        (candle.vwap or Decimal()) * candle.volume for candle in candles
    )
    return weighted / Decimal(volume)


def _return_20(
    closes: Sequence[Decimal], reasons: set[str]
) -> Decimal | None:
    if len(closes) < 21:
        reasons.add("feature_input_missing")
        return None
    base = closes[-21]
    if base == 0:
        reasons.add("feature_division_by_zero")
        return None
    return closes[-1] / base - Decimal(1)


def _flag_current_session_gaps(
    candles: Sequence[NormalizedCandle],
    session: ExchangeSession,
    reasons: set[str],
) -> None:
    if not candles:
        return
    offsets = tuple(_minute_offset(candle, session.market_open) for candle in candles)
    if offsets != tuple(range(offsets[-1] + 1)):
        reasons.add("feature_input_missing")


def _relative_volume_20(
    current: Sequence[NormalizedCandle],
    intraday: Sequence[NormalizedCandle],
    session: ExchangeSession,
    current_volume: int,
    reasons: set[str],
) -> Decimal | None:
    if not current:
        reasons.add("feature_input_missing")
        return None
    target_offset = _minute_offset(current[-1], session.market_open)
    historical: dict[date, list[NormalizedCandle]] = defaultdict(list)
    for candle in intraday:
        session_date = candle.metadata.session_date
        if session_date is not None and session_date < session.session_date:
            historical[session_date].append(candle)

    comparable: list[int] = []
    for session_date in sorted(historical, reverse=True):
        candles = sorted(historical[session_date], key=lambda candle: candle.start)
        market_open = datetime.combine(
            session_date, _XNYS_OPEN, tzinfo=_XNYS_TIMEZONE
        ).astimezone(UTC)
        offsets = tuple(_minute_offset(candle, market_open) for candle in candles)
        required = tuple(range(target_offset + 1))
        if offsets[: target_offset + 1] == required:
            comparable.append(sum(candle.volume for candle in candles[: target_offset + 1]))
        if len(comparable) == 20:
            break
    if len(comparable) < 20:
        reasons.add("feature_input_missing")
        return None
    baseline = median(comparable)
    if baseline == 0:
        reasons.add("feature_division_by_zero")
        return None
    return Decimal(current_volume) / Decimal(baseline)


def _minute_offset(candle: NormalizedCandle, market_open: datetime) -> int:
    return int((candle.start - market_open).total_seconds() // 60)


def _five_minute_bars(
    candles: Sequence[NormalizedCandle], session: ExchangeSession
) -> tuple[FiveMinuteBar, ...]:
    groups: dict[int, list[NormalizedCandle]] = defaultdict(list)
    for candle in candles:
        offset = _minute_offset(candle, session.market_open)
        groups[offset // 5].append(candle)
    result: list[FiveMinuteBar] = []
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda candle: candle.start)
        offsets = tuple(_minute_offset(candle, session.market_open) for candle in group)
        if len(group) != 5 or offsets != tuple(range(key * 5, key * 5 + 5)):
            continue
        result.append(
            FiveMinuteBar(
                start=group[0].start,
                end=group[-1].end,
                open=group[0].open,
                high=max(candle.high for candle in group),
                low=min(candle.low for candle in group),
                close=group[-1].close,
                volume=sum(candle.volume for candle in group),
            )
        )
    return tuple(result)


def assign_relative_performance_percentiles(
    features: Sequence[FeatureResult],
) -> tuple[FeatureResult, ...]:
    valid = sorted(
        (item.return_20, item.symbol)
        for item in features
        if item.return_20 is not None
    )
    count = len(valid)
    output: list[FeatureResult] = []
    for item in features:
        if item.return_20 is None:
            percentile = None
        elif count <= 1:
            percentile = Decimal(0)
        else:
            rank = next(
                index
                for index, value in enumerate(valid)
                if value[0] == item.return_20
            )
            percentile = Decimal(rank) * Decimal(100) / Decimal(count - 1)
        output.append(replace(item, relative_strength_percentile_20=percentile))
    return tuple(sorted(output, key=lambda item: item.symbol))
