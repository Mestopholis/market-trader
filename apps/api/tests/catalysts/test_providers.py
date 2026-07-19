from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from market_trader.catalysts.models import (
    CatalystProviderEvent,
    EventFamily,
    SourceFailure,
    SourceFailureKind,
)
from market_trader.catalysts.providers import (
    AuthorizedSocialProvider,
    AuthorizedSocialRequest,
    CompanyNewsProvider,
    CompanyNewsRequest,
    EarningsProvider,
    EarningsRequest,
    EconomicReleaseProvider,
    EconomicReleaseRequest,
    ProviderBatch,
    SecFilingProvider,
    SecFilingRequest,
    SummaryProvider,
    SummaryRequest,
)

AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)


def _event(family: EventFamily = EventFamily.COMPANY_NEWS) -> CatalystProviderEvent:
    return CatalystProviderEvent(
        source_id="recorded-company-news-v1",
        provider_event_id="event-1",
        event_family=family,
        provider_schema_version=1,
        published_at=AS_OF,
        ingested_at=AS_OF,
        scheduled_for=None,
        symbol_identity="AAPL",
        structured_fields={"category": "product_announcement"},
        external_text={"headline": "Recorded event"},
        source_reference="fixture://company-news/event-1",
        correlation_id="corr-1",
    )


class _ProviderFake:
    def company_news(self, request: CompanyNewsRequest) -> ProviderBatch | SourceFailure:
        return ProviderBatch(
            source_id="recorded-company-news-v1",
            as_of=request.as_of,
            events=(_event(),),
        )

    def earnings(self, request: EarningsRequest) -> ProviderBatch | SourceFailure:
        return ProviderBatch(
            source_id="recorded-earnings-v1",
            as_of=request.as_of,
            events=(_event(EventFamily.EARNINGS),),
        )

    def sec_filings(self, request: SecFilingRequest) -> ProviderBatch | SourceFailure:
        return ProviderBatch(
            source_id="sec-edgar-public-v1",
            as_of=request.as_of,
            events=(_event(EventFamily.SEC_FILING),),
        )

    def economic_releases(
        self, request: EconomicReleaseRequest
    ) -> ProviderBatch | SourceFailure:
        return ProviderBatch(
            source_id="bls-public-v1",
            as_of=request.as_of,
            events=(_event(EventFamily.ECONOMIC_RELEASE),),
        )

    def authorized_social(
        self, request: AuthorizedSocialRequest
    ) -> ProviderBatch | SourceFailure:
        return ProviderBatch(
            source_id="recorded-social-v1",
            as_of=request.as_of,
            events=(_event(EventFamily.SOCIAL),),
        )

    def summarize(self, request: SummaryRequest) -> ProviderBatch | SourceFailure:
        return SourceFailure(
            source_id="recorded-summary-v1",
            kind=SourceFailureKind.UNSUPPORTED,
            occurred_at=request.as_of,
            reasons=("summary_provider_not_configured",),
        )


def test_project_protocols_accept_matching_provider_fakes() -> None:
    provider = _ProviderFake()

    assert isinstance(provider, CompanyNewsProvider)
    assert isinstance(provider, EarningsProvider)
    assert isinstance(provider, SecFilingProvider)
    assert isinstance(provider, EconomicReleaseProvider)
    assert isinstance(provider, AuthorizedSocialProvider)
    assert isinstance(provider, SummaryProvider)


def test_requests_are_immutable_and_canonicalize_allowlisted_identity() -> None:
    symbols = ["MSFT", "AAPL", "AAPL"]
    request = CompanyNewsRequest(as_of=AS_OF, symbols=tuple(symbols))

    symbols.append("TSLA")

    assert request.symbols == ("AAPL", "MSFT")
    with pytest.raises(FrozenInstanceError):
        request.as_of = AS_OF  # type: ignore[misc]


@pytest.mark.parametrize(
    "request_factory",
    (
        lambda as_of: CompanyNewsRequest(as_of=as_of, symbols=("AAPL",)),
        lambda as_of: EarningsRequest(as_of=as_of, symbols=("AAPL",)),
        lambda as_of: SecFilingRequest(as_of=as_of, symbols=("AAPL",)),
        lambda as_of: EconomicReleaseRequest(
            as_of=as_of,
            series_ids=("CUSR0000SA0",),
        ),
        lambda as_of: AuthorizedSocialRequest(
            as_of=as_of,
            account_ids=("authorized-account",),
        ),
        lambda as_of: SummaryRequest(as_of=as_of, observation_keys=("obs-1",)),
    ),
)
def test_requests_reject_naive_as_of(
    request_factory: Callable[[datetime], object],
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        request_factory(datetime(2026, 7, 17, 10, 30))


@pytest.mark.parametrize("kind", tuple(SourceFailureKind))
def test_normal_provider_states_are_explicit_typed_failures(kind: SourceFailureKind) -> None:
    failure = SourceFailure(
        source_id="recorded-company-news-v1",
        kind=kind,
        occurred_at=AS_OF,
        reasons=(f"source_{kind.value}",),
    )

    assert failure.kind is kind
    assert failure.reasons == (f"source_{kind.value}",)


def test_successful_provider_batch_cannot_be_empty_or_cross_source() -> None:
    with pytest.raises(ValueError, match="at least one event"):
        ProviderBatch(source_id="recorded-company-news-v1", as_of=AS_OF, events=())

    with pytest.raises(ValueError, match="source_id"):
        ProviderBatch(source_id="other-source", as_of=AS_OF, events=(_event(),))


def test_provider_batch_is_immutable_and_deterministically_ordered() -> None:
    second = _event()
    first = CatalystProviderEvent(
        **{
            **second.__dict__,
            "provider_event_id": "event-0",
        }
    )
    batch = ProviderBatch(
        source_id="recorded-company-news-v1",
        as_of=AS_OF,
        events=(second, first),
    )

    assert tuple(event.provider_event_id for event in batch.events) == ("event-0", "event-1")
