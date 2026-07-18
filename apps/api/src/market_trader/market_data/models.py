from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
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
