from dataclasses import dataclass
from typing import Protocol

from market_trader.market_data.models import ProviderEvent, QualityState, RejectedObservation
from market_trader.market_data.pipeline import NormalizedObservation
from market_trader.market_data.sanitization import SanitizedValue


@dataclass(frozen=True)
class AcceptedIngestion:
    ingestion_key: str
    payload_digest: str
    sanitized_payload: SanitizedValue
    event: ProviderEvent
    value: NormalizedObservation
    quality_state: QualityState
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RejectedIngestion:
    ingestion_key: str
    payload_digest: str
    sanitized_payload: SanitizedValue
    event: ProviderEvent
    rejection: RejectedObservation


class IngestionSink(Protocol):
    def payload_digest_for(self, ingestion_key: str) -> str | None: ...

    def write_accepted(self, outcome: AcceptedIngestion) -> None: ...

    def write_rejected(self, outcome: RejectedIngestion) -> None: ...


class InMemoryIngestionSink:
    def __init__(self) -> None:
        self._fingerprints: dict[str, str] = {}
        self._accepted: list[AcceptedIngestion] = []
        self._rejected: list[RejectedIngestion] = []

    @property
    def accepted(self) -> tuple[AcceptedIngestion, ...]:
        return tuple(self._accepted)

    @property
    def rejected(self) -> tuple[RejectedIngestion, ...]:
        return tuple(self._rejected)

    def payload_digest_for(self, ingestion_key: str) -> str | None:
        return self._fingerprints.get(ingestion_key)

    def write_accepted(self, outcome: AcceptedIngestion) -> None:
        self._require_new(outcome.ingestion_key)
        self._fingerprints[outcome.ingestion_key] = outcome.payload_digest
        self._accepted.append(outcome)

    def write_rejected(self, outcome: RejectedIngestion) -> None:
        self._require_new(outcome.ingestion_key)
        self._fingerprints[outcome.ingestion_key] = outcome.payload_digest
        self._rejected.append(outcome)

    def _require_new(self, ingestion_key: str) -> None:
        if ingestion_key in self._fingerprints:
            raise ValueError(f"ingestion key already exists: {ingestion_key}")

