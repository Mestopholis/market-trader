from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import NoReturn

from market_trader.domain.time import ensure_utc
from market_trader.market_data.models import (
    DataKind,
    NormalizationResult,
    NormalizedQuote,
    ObservationMetadata,
    ProviderEvent,
    QualityState,
    RejectedObservation,
)


class _NormalizationFailure(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


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


def _metadata(
    event: ProviderEvent,
    state: QualityState,
    reasons: tuple[str, ...],
) -> ObservationMetadata:
    return ObservationMetadata(
        source=event.source,
        event_id=event.event_id,
        observed_at=event.observed_at,
        ingested_at=event.ingested_at,
        session_date=None,
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


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail("invalid_string_list")
    return tuple(value)


def _fail(reason_code: str) -> NoReturn:
    raise _NormalizationFailure(reason_code)
