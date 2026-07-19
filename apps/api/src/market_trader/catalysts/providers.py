from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from market_trader.catalysts.models import CatalystProviderEvent, SourceFailure
from market_trader.domain.time import ensure_utc


@dataclass(frozen=True)
class CompanyNewsRequest:
    as_of: datetime
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(self, "symbols", _identity(self.symbols, "symbol", uppercase=True))


@dataclass(frozen=True)
class EarningsRequest:
    as_of: datetime
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(self, "symbols", _identity(self.symbols, "symbol", uppercase=True))


@dataclass(frozen=True)
class SecFilingRequest:
    as_of: datetime
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(self, "symbols", _identity(self.symbols, "symbol", uppercase=True))


@dataclass(frozen=True)
class EconomicReleaseRequest:
    as_of: datetime
    series_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(
            self,
            "series_ids",
            _identity(self.series_ids, "series_id", uppercase=True),
        )


@dataclass(frozen=True)
class AuthorizedSocialRequest:
    as_of: datetime
    account_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(self, "account_ids", _identity(self.account_ids, "account_id"))


@dataclass(frozen=True)
class SummaryRequest:
    as_of: datetime
    observation_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(
            self,
            "observation_keys",
            _identity(self.observation_keys, "observation_key"),
        )


@dataclass(frozen=True)
class ProviderBatch:
    source_id: str
    as_of: datetime
    events: tuple[CatalystProviderEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        if not self.events:
            raise ValueError("provider batch requires at least one event")
        if any(event.source_id != self.source_id for event in self.events):
            raise ValueError("provider batch source_id must match every event")
        object.__setattr__(
            self,
            "events",
            tuple(sorted(self.events, key=lambda event: event.provider_event_id)),
        )


ProviderOutcome = ProviderBatch | SourceFailure


@runtime_checkable
class CompanyNewsProvider(Protocol):
    def company_news(self, request: CompanyNewsRequest) -> ProviderOutcome: ...


@runtime_checkable
class EarningsProvider(Protocol):
    def earnings(self, request: EarningsRequest) -> ProviderOutcome: ...


@runtime_checkable
class SecFilingProvider(Protocol):
    def sec_filings(self, request: SecFilingRequest) -> ProviderOutcome: ...


@runtime_checkable
class EconomicReleaseProvider(Protocol):
    def economic_releases(self, request: EconomicReleaseRequest) -> ProviderOutcome: ...


@runtime_checkable
class AuthorizedSocialProvider(Protocol):
    def authorized_social(self, request: AuthorizedSocialRequest) -> ProviderOutcome: ...


@runtime_checkable
class SummaryProvider(Protocol):
    def summarize(self, request: SummaryRequest) -> ProviderOutcome: ...


def _identity(
    values: tuple[str, ...],
    label: str,
    *,
    uppercase: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if uppercase:
        normalized = tuple(value.upper() for value in normalized)
    if not normalized or any(not value or len(value) > 128 for value in normalized):
        raise ValueError(f"{label} allowlist must contain bounded nonempty values")
    return tuple(sorted(set(normalized)))

