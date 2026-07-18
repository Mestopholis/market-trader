from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from market_trader.domain.time import ensure_utc


class DataKind(StrEnum):
    QUOTE = "quote"
    CANDLE = "candle"
    OPTION_CHAIN = "option_chain"
    CORPORATE_ACTION = "corporate_action"
    PROVIDER_STATE = "provider_state"


class QualityState(StrEnum):
    VALID = "valid"
    DEGRADED = "degraded"
    STALE = "stale"
    QUARANTINED = "quarantined"


class CandleInterval(StrEnum):
    ONE_MINUTE = "1m"
    DAILY = "1d"


class AdjustmentState(StrEnum):
    ADJUSTED = "adjusted"
    UNADJUSTED = "unadjusted"


@dataclass(frozen=True)
class ProviderEvent:
    source: str
    event_id: str
    data_kind: DataKind
    observed_at: datetime
    ingested_at: datetime
    payload: Mapping[str, object]
    fixture_schema_version: int
    configuration_version: str
    correlation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class ObservationMetadata:
    source: str
    event_id: str
    observed_at: datetime
    ingested_at: datetime
    session_date: date | None
    normalized_schema_version: int
    configuration_version: str
    correlation_id: str
    quality_state: QualityState
    quality_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))
        object.__setattr__(self, "quality_reasons", tuple(sorted(set(self.quality_reasons))))


@dataclass(frozen=True)
class NormalizedQuote:
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    last: Decimal | None
    last_size: int | None
    last_at: datetime | None
    bid_venue: str | None
    ask_venue: str | None
    trade_venue: str | None
    condition_codes: tuple[str, ...]
    metadata: ObservationMetadata


@dataclass(frozen=True)
class NormalizedCandle:
    symbol: str
    interval: CandleInterval
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Decimal | None
    trade_count: int | None
    adjustment: AdjustmentState
    metadata: ObservationMetadata


@dataclass(frozen=True)
class RejectedObservation:
    source: str
    event_id: str
    data_kind: DataKind
    observed_at: datetime
    ingested_at: datetime
    reason_codes: tuple[str, ...]
    quality_state: QualityState = QualityState.QUARANTINED
    symbol_identity: str | None = None
    instrument_identity: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        object.__setattr__(self, "ingested_at", ensure_utc(self.ingested_at))
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))


@dataclass(frozen=True)
class NormalizationResult[NormalizedValue]:
    accepted: NormalizedValue | None = None
    rejection: RejectedObservation | None = None

    def __post_init__(self) -> None:
        if (self.accepted is None) == (self.rejection is None):
            raise ValueError("normalization result requires exactly one outcome")
