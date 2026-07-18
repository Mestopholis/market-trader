from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from market_trader.domain.time import ensure_utc
from market_trader.market_data.models import DataKind, ProviderEvent


@dataclass(frozen=True)
class QuoteRequest:
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class CandleRequest:
    symbols: tuple[str, ...]
    interval: str
    observed_from: datetime
    observed_to: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_from", ensure_utc(self.observed_from))
        object.__setattr__(self, "observed_to", ensure_utc(self.observed_to))


@dataclass(frozen=True)
class OptionChainRequest:
    underlying: str
    expiration_from: date
    expiration_to: date


@dataclass(frozen=True)
class CorporateActionRequest:
    symbol: str
    effective_from: date
    effective_to: date


@dataclass(frozen=True)
class ProviderCapabilities:
    quotes: bool
    candles: bool
    option_chains: bool
    corporate_actions: bool


@dataclass(frozen=True)
class UnsupportedCapability:
    data_kind: DataKind
    reason: str = "unsupported_capability"


class ProviderHealthState(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProviderHealth:
    source: str
    state: ProviderHealthState
    observed_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))


ProviderResponse = tuple[ProviderEvent, ...] | UnsupportedCapability


@runtime_checkable
class QuoteProvider(Protocol):
    def quotes(self, request: QuoteRequest) -> ProviderResponse: ...


@runtime_checkable
class CandleProvider(Protocol):
    def candles(self, request: CandleRequest) -> ProviderResponse: ...


@runtime_checkable
class OptionChainProvider(Protocol):
    def option_chains(self, request: OptionChainRequest) -> ProviderResponse: ...


@runtime_checkable
class CorporateActionProvider(Protocol):
    def corporate_actions(self, request: CorporateActionRequest) -> ProviderResponse: ...


@runtime_checkable
class ProviderStatus(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def health(self) -> ProviderHealth: ...
