from dataclasses import asdict, dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from market_trader.market_data.models import (
    NormalizedOptionChain,
    NormalizedProviderState,
    ProviderEvent,
    QualityState,
    RejectedObservation,
)
from market_trader.market_data.pipeline import NormalizedObservation
from market_trader.market_data.sanitization import SanitizedValue, sanitize_payload
from market_trader.repositories.market_data import (
    MarketDataQuarantineCreate,
    MarketDataRepository,
    MarketDataSnapshotCreate,
)
from market_trader.repositories.symbols import SymbolRepository


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


class ReplayInfrastructureError(RuntimeError):
    pass


class RepositoryIngestionSink:
    def __init__(self, session: Session) -> None:
        self._repository = MarketDataRepository(session)
        self._symbols = SymbolRepository(session)

    def payload_digest_for(self, ingestion_key: str) -> str | None:
        return self._repository.payload_digest_for_ingestion_key(ingestion_key)

    def write_accepted(self, outcome: AcceptedIngestion) -> None:
        if isinstance(outcome.value, NormalizedProviderState):
            raise ReplayInfrastructureError("provider state persistence is unsupported")
        symbol_identity = (
            outcome.value.underlying
            if isinstance(outcome.value, NormalizedOptionChain)
            else outcome.value.symbol
        )
        symbol = self._symbols.get_symbol_by_display_symbol(symbol_identity)
        if symbol is None:
            raise ReplayInfrastructureError(f"unknown symbol: {symbol_identity}")
        payload = sanitize_payload(asdict(outcome.value))
        if not isinstance(payload, dict):
            raise ReplayInfrastructureError("normalized observation is not an object")
        self._repository.store_snapshot(
            MarketDataSnapshotCreate(
                ingestion_key=outcome.ingestion_key,
                payload_digest=outcome.payload_digest,
                event_id=outcome.event.event_id,
                source=outcome.event.source,
                data_kind=outcome.event.data_kind.value,
                symbol_id=symbol.id,
                instrument_id=None,
                observed_at=outcome.event.observed_at,
                ingested_at=outcome.event.ingested_at,
                session_date=outcome.value.metadata.session_date,
                quality_state=outcome.quality_state.value,
                reason_codes=outcome.reason_codes,
                configuration_version_id=None,
                payload=payload,
                payload_schema_version=outcome.value.metadata.normalized_schema_version,
                correlation_id=outcome.event.correlation_id,
            )
        )

    def write_rejected(self, outcome: RejectedIngestion) -> None:
        if not isinstance(outcome.sanitized_payload, dict):
            raise ReplayInfrastructureError("sanitized provider payload is not an object")
        self._repository.quarantine(
            MarketDataQuarantineCreate(
                ingestion_key=outcome.ingestion_key,
                source=outcome.event.source,
                event_id=outcome.event.event_id,
                data_kind=outcome.event.data_kind.value,
                observed_at=outcome.event.observed_at,
                ingested_at=outcome.event.ingested_at,
                symbol_identity=outcome.rejection.symbol_identity,
                instrument_identity=outcome.rejection.instrument_identity,
                sanitized_payload=outcome.sanitized_payload,
                payload_digest=outcome.payload_digest,
                reason_codes=outcome.rejection.reason_codes,
                fixture_schema_version=outcome.event.fixture_schema_version,
                normalized_schema_version=None,
                configuration_version=outcome.event.configuration_version,
                correlation_id=outcome.event.correlation_id,
            )
        )
