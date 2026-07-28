from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.orm import Session

from market_trader.broker.schwab.client import SchwabClientError, SchwabClientState
from market_trader.broker.schwab.normalizers import (
    normalize_schwab_option_chain,
    normalize_schwab_quotes,
)
from market_trader.domain.time import Clock, SystemClock, ensure_utc
from market_trader.market_data.models import DataKind, ProviderEvent
from market_trader.market_data.providers import (
    CandleRequest,
    CorporateActionRequest,
    OptionChainRequest,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthState,
    ProviderResponse,
    QuoteRequest,
    UnsupportedCapability,
)
from market_trader.market_data.sanitization import canonical_digest, sanitize_payload

_SOURCE = "schwab"
_FIXTURE_SCHEMA_VERSION = 1
_CONFIGURATION_VERSION = "schwab-market-data-v1"


class _SchwabJsonClient(Protocol):
    def get_json(
        self,
        session: Session,
        path: str,
        *,
        correlation_id: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]: ...


class SchwabMarketDataProvider:
    def __init__(
        self,
        *,
        client: _SchwabJsonClient,
        session: Session,
        clock: Clock | None = None,
        stale_after: timedelta = timedelta(minutes=15),
    ) -> None:
        self._client = client
        self._session = session
        self._clock = clock or SystemClock()
        self._stale_after = stale_after
        self._last_observed_at: datetime | None = None
        self._last_error_state: SchwabClientState | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            quotes=True,
            candles=True,
            option_chains=True,
            corporate_actions=False,
        )

    def quotes(self, request: QuoteRequest) -> ProviderResponse:
        now = self._now()
        payload = self._get_json(
            "/marketdata/v1/quotes",
            correlation_id="schwab-quotes",
            params={"symbols": ",".join(request.symbols)},
        )
        events = normalize_schwab_quotes(
            payload,
            observed_at=now,
            ingested_at=now,
            correlation_id="schwab-quotes",
        )
        self._record_events(events)
        return events

    def candles(self, request: CandleRequest) -> ProviderResponse:
        now = self._now()
        events: list[ProviderEvent] = []
        for symbol in request.symbols:
            payload = self._get_json(
                "/marketdata/v1/pricehistory",
                correlation_id="schwab-candles",
                params={
                    "symbol": symbol,
                    "startDate": int(request.observed_from.timestamp() * 1000),
                    "endDate": int(request.observed_to.timestamp() * 1000),
                },
            )
            events.extend(
                _candle_events(
                    payload,
                    interval=request.interval,
                    ingested_at=now,
                    correlation_id="schwab-candles",
                )
            )
        result = tuple(events)
        self._record_events(result)
        return result

    def option_chains(self, request: OptionChainRequest) -> ProviderResponse:
        now = self._now()
        payload = self._get_json(
            "/marketdata/v1/chains",
            correlation_id="schwab-option-chains",
            params={
                "symbol": request.underlying,
                "fromDate": request.expiration_from.isoformat(),
                "toDate": request.expiration_to.isoformat(),
            },
        )
        event = normalize_schwab_option_chain(
            payload,
            observed_at=now,
            ingested_at=now,
            correlation_id="schwab-option-chains",
        )
        self._record_events((event,))
        return (event,)

    def corporate_actions(self, _request: CorporateActionRequest) -> UnsupportedCapability:
        return UnsupportedCapability(DataKind.CORPORATE_ACTION)

    def health(self) -> ProviderHealth:
        now = self._now()
        if self._last_error_state is not None:
            state, reason = _health_from_client_state(self._last_error_state)
            return ProviderHealth(
                source=_SOURCE,
                state=state,
                observed_at=now,
                reason_codes=(reason,),
            )
        if (
            self._last_observed_at is not None
            and now - ensure_utc(self._last_observed_at) > self._stale_after
        ):
            return ProviderHealth(
                source=_SOURCE,
                state=ProviderHealthState.DEGRADED,
                observed_at=now,
                reason_codes=("schwab_stale",),
            )
        return ProviderHealth(
            source=_SOURCE,
            state=ProviderHealthState.AVAILABLE,
            observed_at=now,
            reason_codes=(),
        )

    def record_observation(self, observed_at: datetime) -> None:
        self._last_observed_at = ensure_utc(observed_at)
        self._last_error_state = None

    def _get_json(
        self,
        path: str,
        *,
        correlation_id: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        try:
            payload = self._client.get_json(
                self._session,
                path,
                correlation_id=correlation_id,
                params=params,
            )
        except SchwabClientError as error:
            self._last_error_state = error.state
            raise
        self._last_error_state = None
        return payload

    def _record_events(self, events: tuple[ProviderEvent, ...]) -> None:
        if events:
            self.record_observation(max(event.observed_at for event in events))

    def _now(self) -> datetime:
        return ensure_utc(self._clock.now())


def _candle_events(
    payload: Mapping[str, Any],
    *,
    interval: str,
    ingested_at: datetime,
    correlation_id: str,
) -> tuple[ProviderEvent, ...]:
    symbol = str(payload.get("symbol") or "").upper()
    raw_candles = payload.get("candles")
    if not isinstance(raw_candles, list):
        return ()
    events: list[ProviderEvent] = []
    for raw_candle in raw_candles:
        if not isinstance(raw_candle, Mapping):
            continue
        start = _millis_to_datetime(raw_candle.get("datetime"))
        normalized = {
            "symbol": symbol,
            "interval": interval,
            "start": start.isoformat(),
            "end": _candle_end(start, interval).isoformat(),
            "open": _decimal_string(raw_candle.get("open")),
            "high": _decimal_string(raw_candle.get("high")),
            "low": _decimal_string(raw_candle.get("low")),
            "close": _decimal_string(raw_candle.get("close")),
            "volume": _integer(raw_candle.get("volume")),
            "session_date": start.date().isoformat(),
            "adjustment": "unadjusted",
            "schema_version": 1,
        }
        events.append(
            ProviderEvent(
                source=_SOURCE,
                event_id=f"schwab-candle-{canonical_digest(sanitize_payload(normalized))[:16]}",
                data_kind=DataKind.CANDLE,
                observed_at=start,
                ingested_at=ingested_at,
                payload=normalized,
                fixture_schema_version=_FIXTURE_SCHEMA_VERSION,
                configuration_version=_CONFIGURATION_VERSION,
                correlation_id=correlation_id,
            )
        )
    return tuple(events)


def _health_from_client_state(
    state: SchwabClientState,
) -> tuple[ProviderHealthState, str]:
    if state is SchwabClientState.UNAVAILABLE:
        return ProviderHealthState.UNAVAILABLE, "schwab_unavailable"
    if state is SchwabClientState.QUARANTINED:
        return ProviderHealthState.DEGRADED, "schwab_quarantined"
    if state is SchwabClientState.RATE_LIMITED:
        return ProviderHealthState.DEGRADED, "schwab_rate_limited"
    if state is SchwabClientState.AUTH_LOCKED:
        return ProviderHealthState.UNAVAILABLE, "schwab_auth_locked"
    return ProviderHealthState.AVAILABLE, "schwab_available"


def _millis_to_datetime(value: object) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return datetime.fromtimestamp(0, tz=UTC)
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _candle_end(start: datetime, interval: str) -> datetime:
    if interval == "1m":
        return start + timedelta(minutes=1)
    return start + timedelta(days=1)


def _decimal_string(value: object) -> str:
    return "" if value is None else str(value)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)
