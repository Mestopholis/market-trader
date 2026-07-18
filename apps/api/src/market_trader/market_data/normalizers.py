from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import NoReturn

from market_trader.domain.time import ensure_utc
from market_trader.market_data.models import (
    AdjustmentState,
    CandleInterval,
    DataKind,
    DeliverableState,
    NormalizationResult,
    NormalizedCandle,
    NormalizedOptionChain,
    NormalizedOptionContract,
    NormalizedQuote,
    ObservationMetadata,
    ProviderEvent,
    PutCall,
    QualityState,
    RejectedObservation,
)


class _NormalizationFailure(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


_FUTURE_TOLERANCE = timedelta(seconds=5)


def normalize_quote(event: ProviderEvent) -> NormalizationResult[NormalizedQuote]:
    if event.data_kind is not DataKind.QUOTE:
        return NormalizationResult(rejection=_rejection(event, "unexpected_data_kind"))

    try:
        payload = event.payload
        symbol = _required_string(payload, "symbol")
        if any(payload.get(field) is None for field in ("bid", "ask", "bid_size", "ask_size")):
            _fail("missing_top_of_book")
        bid = _decimal(payload["bid"])
        ask = _decimal(payload["ask"])
        bid_size = _integer(payload["bid_size"])
        ask_size = _integer(payload["ask_size"])
        if min(bid, ask) < 0 or min(bid_size, ask_size) < 0:
            _fail("negative_value")
        if ask < bid:
            _fail("crossed_market")

        reasons = ("locked_market",) if ask == bid else ()
        state = QualityState.DEGRADED if reasons else QualityState.VALID
        last = _optional_decimal(payload.get("last"))
        last_size = _optional_integer(payload.get("last_size"))
        if (last is not None and last < 0) or (last_size is not None and last_size < 0):
            _fail("negative_value")

        return NormalizationResult(
            accepted=NormalizedQuote(
                symbol=symbol,
                bid=bid,
                ask=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                last=last,
                last_size=last_size,
                last_at=_optional_datetime(payload.get("last_at")),
                bid_venue=_optional_string(payload.get("bid_venue")),
                ask_venue=_optional_string(payload.get("ask_venue")),
                trade_venue=_optional_string(payload.get("trade_venue")),
                condition_codes=_string_tuple(payload.get("condition_codes", [])),
                metadata=_metadata(event, state, reasons),
            )
        )
    except _NormalizationFailure as error:
        return NormalizationResult(
            rejection=_rejection(
                event,
                error.reason_code,
                symbol_identity=_safe_string(event.payload.get("symbol")),
            )
        )


def normalize_candle(event: ProviderEvent) -> NormalizationResult[NormalizedCandle]:
    if event.data_kind is not DataKind.CANDLE:
        return NormalizationResult(rejection=_rejection(event, "unexpected_data_kind"))

    try:
        payload = event.payload
        symbol = _required_string(payload, "symbol")
        interval = _candle_interval(payload.get("interval"))
        start = _required_datetime(payload.get("start"))
        end = _required_datetime(payload.get("end"))
        if end <= start:
            _fail("invalid_time_range")
        if interval is CandleInterval.ONE_MINUTE and end - start != timedelta(minutes=1):
            _fail("invalid_interval_duration")
        if end > event.ingested_at + _FUTURE_TOLERANCE:
            _fail("future_timestamp")

        open_ = _decimal(payload.get("open"))
        high = _decimal(payload.get("high"))
        low = _decimal(payload.get("low"))
        close = _decimal(payload.get("close"))
        if min(open_, high, low, close) < 0:
            _fail("negative_value")
        if high < max(open_, low, close) or low > min(open_, high, close):
            _fail("inconsistent_ohlc")

        volume = _integer(payload.get("volume"))
        trade_count = _optional_integer(payload.get("trade_count"))
        if volume < 0 or (trade_count is not None and trade_count < 0):
            _fail("negative_value")
        vwap = _optional_decimal(payload.get("vwap"))
        if vwap is not None and vwap < 0:
            _fail("negative_value")

        session_date = _required_date(payload.get("session_date"))
        adjustment = _adjustment_state(payload.get("adjustment"))
        return NormalizationResult(
            accepted=NormalizedCandle(
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                vwap=vwap,
                trade_count=trade_count,
                adjustment=adjustment,
                metadata=_metadata(
                    event,
                    QualityState.VALID,
                    (),
                    session_date=session_date,
                ),
            )
        )
    except _NormalizationFailure as error:
        return NormalizationResult(
            rejection=_rejection(
                event,
                error.reason_code,
                symbol_identity=_safe_string(event.payload.get("symbol")),
            )
        )


def normalize_option_chain(event: ProviderEvent) -> NormalizationResult[NormalizedOptionChain]:
    if event.data_kind is not DataKind.OPTION_CHAIN:
        return NormalizationResult(rejection=_rejection(event, "unexpected_data_kind"))

    try:
        payload = event.payload
        underlying = _required_string(payload, "underlying")
        session_date = _required_date(payload.get("session_date"))
        completeness = payload.get("completeness")
        if completeness not in ("complete", "partial"):
            _fail("invalid_completeness")
        raw_contracts = payload.get("contracts")
        if not isinstance(raw_contracts, list) or not raw_contracts:
            _fail("missing_contracts")

        contracts: list[NormalizedOptionContract] = []
        identities: set[str] = set()
        chain_reasons: set[str] = set()
        if completeness == "partial":
            chain_reasons.add("partial_chain")
        for raw_contract in raw_contracts:
            if not isinstance(raw_contract, Mapping):
                _fail("invalid_contract")
            contract = _normalize_option_contract(raw_contract, session_date)
            if contract.contract_id in identities:
                _fail("duplicate_contract")
            identities.add(contract.contract_id)
            contracts.append(contract)
            chain_reasons.update(contract.quality_reasons)

        reasons = tuple(sorted(chain_reasons))
        state = QualityState.DEGRADED if reasons else QualityState.VALID
        return NormalizationResult(
            accepted=NormalizedOptionChain(
                underlying=underlying,
                is_complete=completeness == "complete",
                contracts=tuple(contracts),
                metadata=_metadata(event, state, reasons, session_date=session_date),
            )
        )
    except _NormalizationFailure as error:
        return NormalizationResult(
            rejection=_rejection(
                event,
                error.reason_code,
                symbol_identity=_safe_string(event.payload.get("underlying")),
            )
        )


def _normalize_option_contract(
    payload: Mapping[str, object],
    session_date: date,
) -> NormalizedOptionContract:
    raw_contract_id = payload.get("contract_id")
    if not isinstance(raw_contract_id, str) or not raw_contract_id.strip():
        _fail("missing_contract_identity")
    contract_id = raw_contract_id.strip()
    expiration = _required_date(payload.get("expiration"))
    if expiration < session_date:
        _fail("invalid_expiration")
    strike = _decimal(payload.get("strike"))
    option_type = _put_call(payload.get("option_type"))
    deliverable = _deliverable_state(payload.get("deliverable"))
    bid = _decimal(payload.get("bid"))
    ask = _decimal(payload.get("ask"))
    bid_size = _integer(payload.get("bid_size"))
    ask_size = _integer(payload.get("ask_size"))
    last = _optional_decimal(payload.get("last"))
    volume = _optional_integer(payload.get("volume"))
    open_interest = _optional_integer(payload.get("open_interest"))
    implied_volatility = _optional_decimal(payload.get("implied_volatility"))

    nonnegative_values = (strike, bid, ask, bid_size, ask_size)
    if any(value < 0 for value in nonnegative_values):
        _fail("negative_value")
    if any(value is not None and value < 0 for value in (last, volume, open_interest)):
        _fail("negative_value")
    if implied_volatility is not None and implied_volatility < 0:
        _fail("negative_value")
    if ask < bid:
        _fail("crossed_market")

    reasons: set[str] = set()
    if ask == bid:
        reasons.add("locked_market")
    if deliverable is DeliverableState.UNSUPPORTED:
        reasons.add("unsupported_deliverable")
    return NormalizedOptionContract(
        contract_id=contract_id,
        expiration=expiration,
        strike=strike,
        option_type=option_type,
        deliverable=deliverable,
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        last=last,
        volume=volume,
        open_interest=open_interest,
        implied_volatility=implied_volatility,
        delta=_optional_decimal(payload.get("delta")),
        gamma=_optional_decimal(payload.get("gamma")),
        theta=_optional_decimal(payload.get("theta")),
        vega=_optional_decimal(payload.get("vega")),
        quality_reasons=tuple(sorted(reasons)),
    )


def _metadata(
    event: ProviderEvent,
    state: QualityState,
    reasons: tuple[str, ...],
    *,
    session_date: date | None = None,
) -> ObservationMetadata:
    return ObservationMetadata(
        source=event.source,
        event_id=event.event_id,
        observed_at=event.observed_at,
        ingested_at=event.ingested_at,
        session_date=session_date,
        normalized_schema_version=1,
        configuration_version=event.configuration_version,
        correlation_id=event.correlation_id,
        quality_state=state,
        quality_reasons=reasons,
    )


def _rejection(
    event: ProviderEvent,
    *reasons: str,
    symbol_identity: str | None = None,
    instrument_identity: str | None = None,
) -> RejectedObservation:
    return RejectedObservation(
        source=event.source,
        event_id=event.event_id,
        data_kind=event.data_kind,
        observed_at=event.observed_at,
        ingested_at=event.ingested_at,
        reason_codes=tuple(reasons),
        symbol_identity=symbol_identity,
        instrument_identity=instrument_identity,
    )


def _decimal(value: object) -> Decimal:
    if isinstance(value, float):
        _fail("binary_float_not_allowed")
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        _fail("invalid_decimal")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        _fail("invalid_decimal")
    if not result.is_finite():
        _fail("invalid_decimal")
    return result


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _integer(value: object) -> int:
    if isinstance(value, bool):
        _fail("invalid_integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    _fail("invalid_integer")


def _optional_integer(value: object) -> int | None:
    return None if value is None else _integer(value)


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail("missing_field")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _fail("invalid_string")
    return value


def _safe_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _fail("invalid_timestamp")
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        _fail("invalid_timestamp")


def _required_datetime(value: object) -> datetime:
    result = _optional_datetime(value)
    if result is None:
        _fail("missing_field")
    return result


def _required_date(value: object) -> date:
    if not isinstance(value, str):
        _fail("missing_field")
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail("invalid_date")


def _candle_interval(value: object) -> CandleInterval:
    if not isinstance(value, str):
        _fail("unsupported_interval")
    try:
        return CandleInterval(value)
    except ValueError:
        _fail("unsupported_interval")


def _adjustment_state(value: object) -> AdjustmentState:
    if not isinstance(value, str):
        _fail("invalid_adjustment_state")
    try:
        return AdjustmentState(value)
    except ValueError:
        _fail("invalid_adjustment_state")


def _put_call(value: object) -> PutCall:
    if not isinstance(value, str):
        _fail("invalid_option_type")
    try:
        return PutCall(value)
    except ValueError:
        _fail("invalid_option_type")


def _deliverable_state(value: object) -> DeliverableState:
    if not isinstance(value, str):
        _fail("invalid_deliverable")
    try:
        return DeliverableState(value)
    except ValueError:
        _fail("invalid_deliverable")


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail("invalid_string_list")
    return tuple(value)


def _fail(reason_code: str) -> NoReturn:
    raise _NormalizationFailure(reason_code)
