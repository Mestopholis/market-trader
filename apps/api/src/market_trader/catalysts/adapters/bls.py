from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import NoReturn, cast

import httpx
from icalendar import Calendar

from market_trader.catalysts.adapters.http import (
    BoundedByteFetcher,
    BoundedJsonFetcher,
    HttpFailure,
    HttpFailureCode,
    RequestLimiter,
)
from market_trader.catalysts.configuration import CatalystConfiguration
from market_trader.catalysts.models import (
    CatalystProviderEvent,
    EventFamily,
    SourceFailure,
    SourceFailureKind,
)
from market_trader.catalysts.providers import EconomicReleaseRequest, ProviderBatch
from market_trader.domain.time import ensure_utc

SOURCE_ID = "bls-public-v1"
SERIES_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
CALENDAR_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
_CALENDAR_CATEGORIES = {
    "Consumer Price Index": "consumer_price_index",
    "The Employment Situation": "employment_situation",
}
_SERIES_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Market-Trader/0.1",
}
_CALENDAR_HEADERS = {
    "Accept": "text/calendar",
    "User-Agent": "Market-Trader/0.1",
}


class _BlsParseFailure(ValueError):
    def __init__(self, kind: SourceFailureKind, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(reason)


class BlsPublicAdapter:
    def __init__(
        self,
        *,
        client: httpx.Client,
        configuration: CatalystConfiguration,
        limiter: RequestLimiter,
        sleeper: Callable[[float], None],
    ) -> None:
        source = configuration.sources.by_id[SOURCE_ID]
        if (
            source.origins != ("https://api.bls.gov", "https://www.bls.gov")
            or source.max_requests != 5
            or source.rate_period_seconds != 60
            or source.daily_request_limit != 20
            or source.allow_redirects
        ):
            raise ValueError("BLS source policy is invalid")
        self._configuration = configuration
        self._json_fetcher = BoundedJsonFetcher(
            client=client,
            source_id=SOURCE_ID,
            allowed_origins=source.origins,
            limiter=limiter,
            sleeper=sleeper,
            max_response_bytes=source.max_response_bytes,
        )
        self._byte_fetcher = BoundedByteFetcher(
            client=client,
            source_id=SOURCE_ID,
            allowed_origins=source.origins,
            limiter=limiter,
            sleeper=sleeper,
            max_response_bytes=source.max_response_bytes,
        )

    def economic_releases(
        self,
        request: EconomicReleaseRequest,
    ) -> ProviderBatch | SourceFailure:
        expected = tuple(sorted(self._configuration.sources.bls_series.values()))
        if request.series_ids != expected:
            return self._failure(
                request,
                SourceFailureKind.UNSUPPORTED,
                "bls_series_allowlist_mismatch",
            )
        series_result = self._json_fetcher.post(
            SERIES_URL,
            headers=_SERIES_HEADERS,
            json_payload={"seriesid": list(request.series_ids)},
        )
        if series_result.failure is not None:
            return self._http_failure(request, series_result.failure)
        try:
            series_events = _parse_series(
                series_result.payload,
                configuration=self._configuration,
                as_of=request.as_of,
            )
        except _BlsParseFailure as error:
            return self._failure(request, error.kind, error.reason)

        calendar_result = self._byte_fetcher.request(
            "GET",
            CALENDAR_URL,
            headers=_CALENDAR_HEADERS,
        )
        if calendar_result.failure is not None:
            return self._http_failure(request, calendar_result.failure)
        try:
            schedule_events = _parse_calendar(
                calendar_result.payload or b"",
                as_of=request.as_of,
            )
        except _BlsParseFailure as error:
            return self._failure(request, SourceFailureKind.PARTIAL, error.reason)
        return ProviderBatch(
            source_id=SOURCE_ID,
            as_of=request.as_of,
            events=series_events + schedule_events,
        )

    def _http_failure(
        self,
        request: EconomicReleaseRequest,
        failure: HttpFailure,
    ) -> SourceFailure:
        if failure.code is HttpFailureCode.HTTP_STATUS:
            reason = f"bls_http_{failure.status_code}"
        else:
            reason = f"bls_{failure.code.value}"
        return self._failure(request, failure.kind, reason)

    @staticmethod
    def _failure(
        request: EconomicReleaseRequest,
        kind: SourceFailureKind,
        reason: str,
    ) -> SourceFailure:
        return SourceFailure(
            source_id=SOURCE_ID,
            kind=kind,
            occurred_at=request.as_of,
            reasons=(reason,),
        )


def _parse_series(
    payload: object,
    *,
    configuration: CatalystConfiguration,
    as_of: datetime,
) -> tuple[CatalystProviderEvent, ...]:
    root = _mapping(payload, "bls_series_schema_drift")
    status = root.get("status")
    if status != "REQUEST_SUCCEEDED":
        _parse_fail(SourceFailureKind.UNAVAILABLE, "bls_status_error")
    results = _mapping(root.get("Results"), "bls_series_schema_drift")
    raw_series = _list(results.get("series"), "bls_series_schema_drift")
    by_id: dict[str, Mapping[str, object]] = {}
    for raw in raw_series:
        series = _mapping(raw, "bls_series_schema_drift")
        series_id = _string(series.get("seriesID"), "bls_series_schema_drift")
        if series_id in by_id:
            _parse_fail(SourceFailureKind.MALFORMED, "bls_duplicate_series")
        by_id[series_id] = series
    categories = {
        series_id: category
        for category, series_id in configuration.sources.bls_series.items()
    }
    if set(by_id) != set(categories):
        _parse_fail(SourceFailureKind.PARTIAL, "bls_series_partial")
    events: list[CatalystProviderEvent] = []
    for series_id, category in sorted(categories.items()):
        data = _list(by_id[series_id].get("data"), "bls_series_schema_drift")
        if not data:
            _parse_fail(SourceFailureKind.PARTIAL, "bls_series_partial")
        record = _mapping(data[0], "bls_series_schema_drift")
        year = _year(record.get("year"))
        period = _period(record.get("period"))
        value = _decimal_string(record.get("value"))
        event_id = f"series:{series_id}:{year}:{period}"
        events.append(
            CatalystProviderEvent(
                source_id=SOURCE_ID,
                provider_event_id=event_id,
                event_family=EventFamily.ECONOMIC_RELEASE,
                provider_schema_version=1,
                published_at=as_of,
                ingested_at=as_of,
                scheduled_for=None,
                symbol_identity=None,
                structured_fields={
                    "event_category": category,
                    "period": f"{year}-{period}",
                    "series_id": series_id,
                    "value": value,
                },
                external_text={"period_name": record.get("periodName", "")},
                source_reference=f"{SERIES_URL}#{event_id}",
                correlation_id=f"bls:{series_id}:{year}:{period}",
            )
        )
    return tuple(events)


def _parse_calendar(payload: bytes, *, as_of: datetime) -> tuple[CatalystProviderEvent, ...]:
    try:
        calendar = Calendar.from_ical(payload)
    except (ValueError, TypeError):
        _parse_fail(SourceFailureKind.MALFORMED, "bls_calendar_malformed")
    identities: dict[str, tuple[str, datetime]] = {}
    events: list[CatalystProviderEvent] = []
    try:
        components = calendar.walk("VEVENT")
    except (AttributeError, ValueError, TypeError):
        _parse_fail(SourceFailureKind.MALFORMED, "bls_calendar_malformed")
    for component in components:
        if getattr(component, "errors", ()):
            _parse_fail(SourceFailureKind.MALFORMED, "bls_calendar_malformed")
        summary_value = component.get("SUMMARY")
        if summary_value is None:
            continue
        summary = str(summary_value)
        category = _CALENDAR_CATEGORIES.get(summary)
        if category is None:
            continue
        uid_value = component.get("UID")
        start_value = component.get("DTSTART")
        if uid_value is None or start_value is None:
            _parse_fail(
                SourceFailureKind.MALFORMED,
                "bls_calendar_required_property_missing",
            )
        uid = str(uid_value).strip()
        scheduled = getattr(start_value, "dt", None)
        if not uid or not isinstance(scheduled, datetime) or scheduled.tzinfo is None:
            _parse_fail(
                SourceFailureKind.MALFORMED,
                "bls_calendar_required_property_missing",
            )
        scheduled_at = ensure_utc(scheduled)
        identity = (category, scheduled_at)
        existing = identities.get(uid)
        if existing is not None:
            if existing != identity:
                _parse_fail(
                    SourceFailureKind.MALFORMED,
                    "bls_calendar_uid_conflict",
                )
            continue
        identities[uid] = identity
        event_id = f"schedule:{uid}:{category}"
        events.append(
            CatalystProviderEvent(
                source_id=SOURCE_ID,
                provider_event_id=event_id,
                event_family=EventFamily.ECONOMIC_RELEASE,
                provider_schema_version=1,
                published_at=as_of,
                ingested_at=as_of,
                scheduled_for=scheduled_at,
                symbol_identity=None,
                structured_fields={
                    "calendar_uid": uid,
                    "event_category": category,
                    "release_title": summary,
                },
                external_text={},
                source_reference=f"{CALENDAR_URL}#{uid}",
                correlation_id=f"bls:{uid}",
            )
        )
    return tuple(events)


def _mapping(value: object, reason: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _parse_fail(SourceFailureKind.MALFORMED, reason)
    return cast(Mapping[str, object], value)


def _list(value: object, reason: str) -> list[object]:
    if not isinstance(value, list):
        _parse_fail(SourceFailureKind.MALFORMED, reason)
    return value


def _string(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value:
        _parse_fail(SourceFailureKind.MALFORMED, reason)
    return value


def _year(value: object) -> str:
    raw = _string(value, "bls_invalid_year")
    if len(raw) != 4 or not raw.isdigit():
        _parse_fail(SourceFailureKind.MALFORMED, "bls_invalid_year")
    return raw


def _period(value: object) -> str:
    raw = _string(value, "bls_invalid_period")
    if len(raw) != 3 or raw[0] != "M" or not raw[1:].isdigit():
        _parse_fail(SourceFailureKind.MALFORMED, "bls_invalid_period")
    month = int(raw[1:])
    if not 1 <= month <= 12:
        _parse_fail(SourceFailureKind.MALFORMED, "bls_invalid_period")
    return raw


def _decimal_string(value: object) -> str:
    if not isinstance(value, str):
        _parse_fail(SourceFailureKind.MALFORMED, "bls_invalid_value")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _parse_fail(SourceFailureKind.MALFORMED, "bls_invalid_value")
    if not parsed.is_finite():
        _parse_fail(SourceFailureKind.MALFORMED, "bls_invalid_value")
    return format(parsed, "f")


def _parse_fail(kind: SourceFailureKind, reason: str) -> NoReturn:
    raise _BlsParseFailure(kind, reason)
