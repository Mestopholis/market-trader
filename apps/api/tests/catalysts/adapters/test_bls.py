import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from market_trader.catalysts.adapters.bls import BlsPublicAdapter
from market_trader.catalysts.configuration import load_catalyst_configuration
from market_trader.catalysts.models import SourceFailure, SourceFailureKind
from market_trader.catalysts.providers import EconomicReleaseRequest, ProviderBatch
from tests.catalysts.adapters.test_sec import RecordingLimiter

API_ROOT = Path(__file__).parents[3]
FIXTURES = Path(__file__).parents[1] / "fixtures" / "http"
CONFIGURATION = load_catalyst_configuration(API_ROOT / "config" / "catalysts")
AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)
SERIES_IDS = tuple(sorted(CONFIGURATION.sources.bls_series.values()))


def _series_fixture() -> dict[str, object]:
    value = json.loads((FIXTURES / "bls-series.json").read_text())
    assert isinstance(value, dict)
    return value


def _calendar_fixture() -> bytes:
    return (FIXTURES / "bls-calendar.ics").read_bytes()


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        timeout=httpx.Timeout(20.0, connect=10.0),
    )


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    limiter: RecordingLimiter | None = None,
    sleeps: list[float] | None = None,
) -> BlsPublicAdapter:
    recorded_sleeps = sleeps if sleeps is not None else []
    return BlsPublicAdapter(
        client=_client(handler),
        configuration=CONFIGURATION,
        limiter=limiter or RecordingLimiter(),
        sleeper=recorded_sleeps.append,
    )


def _success_handler(requests: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "api.bls.gov":
            return httpx.Response(200, json=_series_fixture())
        return httpx.Response(200, content=_calendar_fixture())

    return handler


def test_fetches_exact_unregistered_series_and_official_calendar() -> None:
    requests: list[httpx.Request] = []
    limiter = RecordingLimiter()
    outcome = _adapter(_success_handler(requests), limiter=limiter).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )

    assert isinstance(outcome, ProviderBatch)
    assert [(request.method, request.url.host, request.url.path) for request in requests] == [
        ("POST", "api.bls.gov", "/publicAPI/v1/timeseries/data/"),
        ("GET", "www.bls.gov", "/schedule/news_release/bls.ics"),
    ]
    request_payload = json.loads(requests[0].content)
    assert request_payload == {"seriesid": list(SERIES_IDS)}
    assert "registrationkey" not in request_payload
    assert all("authorization" not in request.headers for request in requests)
    assert all("cookie" not in request.headers for request in requests)
    assert limiter.calls == ["bls-public-v1", "bls-public-v1"]
    categories = {event.structured_fields["event_category"] for event in outcome.events}
    assert categories == {
        "consumer_price_index",
        "employment_situation",
        "total_nonfarm_payrolls",
        "unemployment_rate",
    }


def test_calendar_times_convert_eastern_to_utc_across_dst() -> None:
    outcome = _adapter(_success_handler([])).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )

    assert isinstance(outcome, ProviderBatch)
    scheduled = {
        event.provider_event_id: event.scheduled_for
        for event in outcome.events
        if event.scheduled_for is not None
    }
    assert scheduled["schedule:cpi-july-2026:consumer_price_index"] == datetime(
        2026, 7, 14, 12, 30, tzinfo=UTC
    )
    assert scheduled["schedule:empsit-december-2026:employment_situation"] == datetime(
        2026, 12, 4, 13, 30, tzinfo=UTC
    )


def test_unknown_calendar_titles_are_ignored_and_exact_duplicates_deduplicate() -> None:
    outcome = _adapter(_success_handler([])).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )

    assert isinstance(outcome, ProviderBatch)
    schedule_ids = [
        event.provider_event_id
        for event in outcome.events
        if event.provider_event_id.startswith("schedule:")
    ]
    assert schedule_ids == [
        "schedule:cpi-july-2026:consumer_price_index",
        "schedule:empsit-december-2026:employment_situation",
    ]


def test_requires_exact_configured_series_allowlist_without_network() -> None:
    requests: list[httpx.Request] = []
    outcome = _adapter(_success_handler(requests)).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=("CUSR0000SA0",))
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.UNSUPPORTED
    assert outcome.reasons == ("bls_series_allowlist_mismatch",)
    assert requests == []


def test_source_policy_pins_five_per_minute_twenty_per_day_and_two_megabytes() -> None:
    source = CONFIGURATION.sources.by_id["bls-public-v1"]

    assert source.max_requests == 5
    assert source.rate_period_seconds == 60
    assert source.daily_request_limit == 20
    assert source.max_response_bytes == 2 * 1024 * 1024
    assert source.allow_redirects is False


def test_partial_series_returns_explicit_partial_failure() -> None:
    payload = _series_fixture()
    series = payload["Results"]["series"]  # type: ignore[index]
    series.pop()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.bls.gov":
            return httpx.Response(200, json=payload)
        return httpx.Response(200, content=_calendar_fixture())

    outcome = _adapter(handler).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.PARTIAL
    assert outcome.reasons == ("bls_series_partial",)


def test_bls_status_error_is_unavailable() -> None:
    payload = {"status": "REQUEST_FAILED", "message": ["Request could not be serviced"]}
    outcome = _adapter(lambda request: httpx.Response(200, json=payload)).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.UNAVAILABLE
    assert outcome.reasons == ("bls_status_error",)


@pytest.mark.parametrize(
    ("calendar", "reason"),
    (
        (b"not-an-icalendar", "bls_calendar_malformed"),
        (
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
            b"SUMMARY:Consumer Price Index\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
            "bls_calendar_required_property_missing",
        ),
    ),
)
def test_malformed_or_broken_calendar_is_explicit_partial(
    calendar: bytes,
    reason: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.bls.gov":
            return httpx.Response(200, json=_series_fixture())
        return httpx.Response(200, content=calendar)

    outcome = _adapter(handler).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.PARTIAL
    assert outcome.reasons == (reason,)


def test_conflicting_duplicate_schedule_uid_is_partial() -> None:
    calendar = _calendar_fixture().replace(
        b"END:VCALENDAR",
        b"BEGIN:VEVENT\r\nUID:cpi-july-2026\r\n"
        b"DTSTART;TZID=America/New_York:20260715T083000\r\n"
        b"SUMMARY:Consumer Price Index\r\nEND:VEVENT\r\nEND:VCALENDAR",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.bls.gov":
            return httpx.Response(200, json=_series_fixture())
        return httpx.Response(200, content=calendar)

    outcome = _adapter(handler).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.PARTIAL
    assert outcome.reasons == ("bls_calendar_uid_conflict",)


def test_remote_and_local_throttling_are_typed_and_bounded() -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def throttled(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "999"})

    remote = _adapter(throttled, sleeps=sleeps).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )
    local = _adapter(
        _success_handler([]),
        limiter=RecordingLimiter(allowed=False),
    ).economic_releases(EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS))

    assert isinstance(remote, SourceFailure)
    assert remote.kind is SourceFailureKind.THROTTLED
    assert remote.reasons == ("bls_http_429",)
    assert len(requests) == 3
    assert all(delay <= 5.0 for delay in sleeps)
    assert isinstance(local, SourceFailure)
    assert local.kind is SourceFailureKind.THROTTLED
    assert local.reasons == ("bls_local_rate_limit",)


def test_timeout_retries_and_two_megabyte_bound_fail_closed() -> None:
    requests: list[httpx.Request] = []

    def timeout(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    timed_out = _adapter(timeout).economic_releases(
        EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
    )
    oversized = _adapter(
        lambda request: httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))
    ).economic_releases(EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS))

    assert isinstance(timed_out, SourceFailure)
    assert timed_out.kind is SourceFailureKind.UNAVAILABLE
    assert timed_out.reasons == ("bls_timeout",)
    assert len(requests) == 3
    assert isinstance(oversized, SourceFailure)
    assert oversized.kind is SourceFailureKind.SECURITY_REJECTED
    assert oversized.reasons == ("bls_response_too_large",)


def test_malformed_series_json_and_schema_are_malformed() -> None:
    outcomes = (
        _adapter(lambda request: httpx.Response(200, content=b"not-json")).economic_releases(
            EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)
        ),
        _adapter(
            lambda request: httpx.Response(
                200,
                json={"status": "REQUEST_SUCCEEDED"},
            )
        ).economic_releases(EconomicReleaseRequest(as_of=AS_OF, series_ids=SERIES_IDS)),
    )

    for outcome in outcomes:
        assert isinstance(outcome, SourceFailure)
        assert outcome.kind is SourceFailureKind.MALFORMED
