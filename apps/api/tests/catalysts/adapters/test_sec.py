import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from market_trader.catalysts.adapters.http import RequestLimiter
from market_trader.catalysts.adapters.sec import SecEdgarAdapter
from market_trader.catalysts.configuration import load_catalyst_configuration
from market_trader.catalysts.models import EventFamily, SourceFailure, SourceFailureKind
from market_trader.catalysts.providers import ProviderBatch, SecFilingRequest

API_ROOT = Path(__file__).parents[3]
FIXTURES = Path(__file__).parents[1] / "fixtures" / "http"
CONFIGURATION = load_catalyst_configuration(API_ROOT / "config" / "catalysts")
AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)
USER_AGENT = "Market Trader catalyst research developer@example.com"


class RecordingLimiter(RequestLimiter):
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[str] = []

    def acquire(self, source_id: str) -> bool:
        self.calls.append(source_id)
        return self.allowed


def _json_fixture(name: str) -> dict[str, object]:
    value = json.loads((FIXTURES / name).read_text())
    assert isinstance(value, dict)
    return value


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
) -> SecEdgarAdapter:
    recorded_sleeps = sleeps if sleeps is not None else []
    return SecEdgarAdapter(
        client=_client(handler),
        configuration=CONFIGURATION,
        user_agent=USER_AGENT,
        limiter=limiter or RecordingLimiter(),
        sleeper=recorded_sleeps.append,
    )


def test_fetches_only_fixed_sec_resources_with_identified_safe_headers() -> None:
    requests: list[httpx.Request] = []
    submissions = _json_fixture("sec-submissions.json")
    companyfacts = _json_fixture("sec-companyfacts.json")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = companyfacts if "companyfacts" in request.url.path else submissions
        return httpx.Response(200, json=payload)

    limiter = RecordingLimiter()
    outcome = _adapter(handler, limiter=limiter).sec_filings(
        SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
    )

    assert isinstance(outcome, ProviderBatch)
    assert {event.event_family for event in outcome.events} == {EventFamily.SEC_FILING}
    order = tuple((event.published_at, event.provider_event_id) for event in outcome.events)
    assert order == tuple(sorted(order))
    forms = {
        event.structured_fields["form"]
        for event in outcome.events
        if "accession_number" in event.structured_fields
    }
    assert forms == {"8-K", "8-K/A", "10-Q", "10-K", "6-K", "20-F", "40-F"}
    assert any("fact_name" in event.structured_fields for event in outcome.events)
    assert [request.method for request in requests] == ["GET", "GET"]
    assert [request.url.host for request in requests] == ["data.sec.gov", "data.sec.gov"]
    assert [request.url.path for request in requests] == [
        "/submissions/CIK0000320193.json",
        "/api/xbrl/companyfacts/CIK0000320193.json",
    ]
    assert all(request.headers["user-agent"] == USER_AGENT for request in requests)
    assert all(request.headers["accept"] == "application/json" for request in requests)
    assert all(request.headers["accept-encoding"] == "gzip, deflate" for request in requests)
    assert all("authorization" not in request.headers for request in requests)
    assert all("cookie" not in request.headers for request in requests)
    assert limiter.calls == ["sec-edgar-public-v1", "sec-edgar-public-v1"]


def test_unsupported_fund_is_explicit_without_network_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    outcome = _adapter(handler).sec_filings(
        SecFilingRequest(as_of=AS_OF, symbols=("SPY",))
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.UNSUPPORTED
    assert outcome.reasons == ("sec_symbol_unsupported",)
    assert requests == []


@pytest.mark.parametrize(
    ("follow_redirects", "timeout", "message"),
    (
        (True, httpx.Timeout(20.0, connect=10.0), "redirect"),
        (False, httpx.Timeout(21.0, connect=10.0), "timeout"),
        (False, httpx.Timeout(20.0, connect=11.0), "timeout"),
    ),
)
def test_rejects_clients_that_weaken_redirect_or_timeout_policy(
    follow_redirects: bool,
    timeout: httpx.Timeout,
    message: str,
) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        follow_redirects=follow_redirects,
        timeout=timeout,
    )

    with pytest.raises(ValueError, match=message):
        SecEdgarAdapter(
            client=client,
            configuration=CONFIGURATION,
            user_agent=USER_AGENT,
            limiter=RecordingLimiter(),
            sleeper=lambda _: None,
        )


def test_rejects_unidentified_or_header_injecting_user_agent() -> None:
    handler = lambda request: httpx.Response(200)  # noqa: E731

    for user_agent in ("Market Trader", "Market Trader dev@example.com\r\nCookie: secret"):
        with pytest.raises(ValueError, match="User-Agent"):
            SecEdgarAdapter(
                client=_client(handler),
                configuration=CONFIGURATION,
                user_agent=user_agent,
                limiter=RecordingLimiter(),
                sleeper=lambda _: None,
            )


def test_enforces_ten_megabyte_response_bound() -> None:
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    outcome = _adapter(lambda request: httpx.Response(200, content=oversized)).sec_filings(
        SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.SECURITY_REJECTED
    assert outcome.reasons == ("sec_response_too_large",)


def test_partial_submission_columns_are_explicit_partial_failure() -> None:
    payload = _json_fixture("sec-submissions.json")
    recent = payload["filings"]["recent"]  # type: ignore[index]
    del recent["acceptanceDateTime"]

    outcome = _adapter(lambda request: httpx.Response(200, json=payload)).sec_filings(
        SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.PARTIAL
    assert outcome.reasons == ("sec_submission_columns_partial",)


def test_mismatched_submission_column_lengths_are_malformed() -> None:
    payload = _json_fixture("sec-submissions.json")
    recent = payload["filings"]["recent"]  # type: ignore[index]
    recent["form"] = ["8-K"]

    outcome = _adapter(lambda request: httpx.Response(200, json=payload)).sec_filings(
        SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.MALFORMED
    assert outcome.reasons == ("sec_submission_column_length_mismatch",)


@pytest.mark.parametrize(
    ("status_code", "kind", "reason", "expected_requests"),
    (
        (403, SourceFailureKind.UNAVAILABLE, "sec_http_403", 1),
        (429, SourceFailureKind.THROTTLED, "sec_http_429", 3),
        (503, SourceFailureKind.UNAVAILABLE, "sec_http_503", 3),
    ),
)
def test_maps_http_failures_and_bounds_retries(
    status_code: int,
    kind: SourceFailureKind,
    reason: str,
    expected_requests: int,
) -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, headers={"Retry-After": "999"})

    outcome = _adapter(handler, sleeps=sleeps).sec_filings(
        SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is kind
    assert outcome.reasons == (reason,)
    assert len(requests) == expected_requests
    assert all(delay <= 5.0 for delay in sleeps)


def test_retries_timeouts_twice_then_returns_unavailable() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    outcome = _adapter(handler).sec_filings(
        SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
    )

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.UNAVAILABLE
    assert outcome.reasons == ("sec_timeout",)
    assert len(requests) == 3


def test_limiter_denial_is_explicit_throttling() -> None:
    limiter = RecordingLimiter(allowed=False)
    outcome = _adapter(
        lambda request: httpx.Response(200),
        limiter=limiter,
    ).sec_filings(SecFilingRequest(as_of=AS_OF, symbols=("AAPL",)))

    assert isinstance(outcome, SourceFailure)
    assert outcome.kind is SourceFailureKind.THROTTLED
    assert outcome.reasons == ("sec_local_rate_limit",)
    assert limiter.calls == ["sec-edgar-public-v1"]


def test_schema_drift_and_invalid_json_are_malformed() -> None:
    outcomes = (
        _adapter(lambda request: httpx.Response(200, json={"unexpected": {}})).sec_filings(
            SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
        ),
        _adapter(lambda request: httpx.Response(200, content=b"not-json")).sec_filings(
            SecFilingRequest(as_of=AS_OF, symbols=("AAPL",))
        ),
    )

    for outcome in outcomes:
        assert isinstance(outcome, SourceFailure)
        assert outcome.kind is SourceFailureKind.MALFORMED
