from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import MarketDataQuarantineORM, MarketDataSnapshotORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc
from market_trader.market_data.sanitization import canonical_digest, sanitize_payload
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


class IngestionConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketDataSnapshotCreate:
    source: str
    symbol_id: str
    instrument_id: str | None
    observed_at: datetime
    ingested_at: datetime
    session_date: date | None
    quality_state: str
    configuration_version_id: str | None
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str
    ingestion_key: str | None = None
    data_kind: str = "legacy"
    payload_digest: str | None = None
    event_id: str | None = None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketDataSnapshot:
    id: str
    ingestion_key: str
    payload_digest: str
    source: str
    data_kind: str
    symbol_id: str
    instrument_id: str | None
    observed_at: datetime
    ingested_at: datetime
    session_date: date | None
    quality_state: str
    configuration_version_id: str | None
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str


@dataclass(frozen=True)
class MarketDataQuarantineCreate:
    ingestion_key: str
    source: str
    event_id: str
    data_kind: str
    observed_at: datetime
    ingested_at: datetime
    symbol_identity: str | None
    instrument_identity: str | None
    sanitized_payload: dict[str, Any]
    payload_digest: str
    reason_codes: tuple[str, ...]
    fixture_schema_version: int
    normalized_schema_version: int | None
    configuration_version: str
    correlation_id: str


@dataclass(frozen=True)
class MarketDataQuarantine:
    id: str
    ingestion_key: str
    source: str
    event_id: str
    data_kind: str
    observed_at: datetime
    ingested_at: datetime
    symbol_identity: str | None
    instrument_identity: str | None
    sanitized_payload: dict[str, Any]
    payload_digest: str
    reason_codes: tuple[str, ...]
    fixture_schema_version: int
    normalized_schema_version: int | None
    configuration_version: str
    correlation_id: str
    created_at: datetime


class MarketDataRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def store_snapshot(self, command: MarketDataSnapshotCreate) -> MarketDataSnapshot:
        record_id = new_domain_id("mds")
        ingestion_key = command.ingestion_key or f"legacy:{record_id}"
        payload_digest = command.payload_digest or canonical_digest(
            sanitize_payload(command.payload)
        )
        existing = self.get_snapshot_by_ingestion_key(ingestion_key)
        if existing is not None:
            self._require_matching_digest(ingestion_key, existing.payload_digest, payload_digest)
            return existing

        record = MarketDataSnapshotORM(
            id=record_id,
            ingestion_key=ingestion_key,
            payload_digest=payload_digest,
            source=command.source,
            data_kind=command.data_kind,
            symbol_id=command.symbol_id,
            instrument_id=command.instrument_id,
            observed_at=ensure_utc(command.observed_at),
            ingested_at=ensure_utc(command.ingested_at),
            session_date=command.session_date,
            quality_state=command.quality_state,
            configuration_version_id=command.configuration_version_id,
            payload=dict(command.payload),
            payload_schema_version=command.payload_schema_version,
            correlation_id=command.correlation_id,
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="market_data_snapshot.stored",
                actor_type="system",
                occurred_at=command.ingested_at,
                subject_type="market_data_snapshot",
                subject_id=record.id,
                payload={
                    "schema_version": 1,
                    "source": command.source,
                    "event_id": command.event_id,
                    "data_kind": command.data_kind,
                    "ingestion_key": ingestion_key,
                    "payload_digest": payload_digest,
                    "symbol_id": command.symbol_id,
                    "quality_state": command.quality_state,
                    "reason_codes": list(sorted(set(command.reason_codes))),
                },
                schema_version=1,
            )
        )
        return _snapshot_to_domain(record)

    def quarantine(self, command: MarketDataQuarantineCreate) -> MarketDataQuarantine:
        existing = self.get_quarantine_by_ingestion_key(command.ingestion_key)
        if existing is not None:
            self._require_matching_digest(
                command.ingestion_key,
                existing.payload_digest,
                command.payload_digest,
            )
            return existing

        record = MarketDataQuarantineORM(
            id=new_domain_id("mdq"),
            ingestion_key=command.ingestion_key,
            source=command.source,
            event_id=command.event_id,
            data_kind=command.data_kind,
            observed_at=ensure_utc(command.observed_at),
            ingested_at=ensure_utc(command.ingested_at),
            symbol_identity=command.symbol_identity,
            instrument_identity=command.instrument_identity,
            sanitized_payload=dict(command.sanitized_payload),
            payload_digest=command.payload_digest,
            reason_codes=list(sorted(set(command.reason_codes))),
            fixture_schema_version=command.fixture_schema_version,
            normalized_schema_version=command.normalized_schema_version,
            configuration_version=command.configuration_version,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.ingested_at),
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="market_data_observation.quarantined",
                actor_type="system",
                occurred_at=command.ingested_at,
                subject_type="market_data_quarantine",
                subject_id=record.id,
                payload={
                    "schema_version": 1,
                    "source": command.source,
                    "event_id": command.event_id,
                    "data_kind": command.data_kind,
                    "ingestion_key": command.ingestion_key,
                    "payload_digest": command.payload_digest,
                    "reason_codes": list(sorted(set(command.reason_codes))),
                },
                schema_version=1,
            )
        )
        return _quarantine_to_domain(record)

    def get_snapshot_by_ingestion_key(self, ingestion_key: str) -> MarketDataSnapshot | None:
        record = self._session.scalar(
            select(MarketDataSnapshotORM).where(
                MarketDataSnapshotORM.ingestion_key == ingestion_key
            )
        )
        return _snapshot_to_domain(record) if record is not None else None

    def get_quarantine_by_ingestion_key(
        self,
        ingestion_key: str,
    ) -> MarketDataQuarantine | None:
        record = self._session.scalar(
            select(MarketDataQuarantineORM).where(
                MarketDataQuarantineORM.ingestion_key == ingestion_key
            )
        )
        return _quarantine_to_domain(record) if record is not None else None

    def payload_digest_for_ingestion_key(self, ingestion_key: str) -> str | None:
        snapshot_digest = self._session.scalar(
            select(MarketDataSnapshotORM.payload_digest).where(
                MarketDataSnapshotORM.ingestion_key == ingestion_key
            )
        )
        if snapshot_digest is not None:
            return snapshot_digest
        return self._session.scalar(
            select(MarketDataQuarantineORM.payload_digest).where(
                MarketDataQuarantineORM.ingestion_key == ingestion_key
            )
        )

    def list_snapshots(
        self,
        *,
        symbol_id: str,
        source: str,
        observed_from: datetime,
        observed_to: datetime,
    ) -> list[MarketDataSnapshot]:
        records = self._session.scalars(
            select(MarketDataSnapshotORM)
            .where(
                MarketDataSnapshotORM.symbol_id == symbol_id,
                MarketDataSnapshotORM.source == source,
                MarketDataSnapshotORM.observed_at >= ensure_utc(observed_from),
                MarketDataSnapshotORM.observed_at <= ensure_utc(observed_to),
            )
            .order_by(MarketDataSnapshotORM.observed_at, MarketDataSnapshotORM.id)
        )
        return [_snapshot_to_domain(record) for record in records]

    @staticmethod
    def _require_matching_digest(
        ingestion_key: str,
        existing_digest: str,
        requested_digest: str,
    ) -> None:
        if existing_digest != requested_digest:
            raise IngestionConflictError(f"ingestion key conflict: {ingestion_key}")


def _snapshot_to_domain(record: MarketDataSnapshotORM) -> MarketDataSnapshot:
    return MarketDataSnapshot(
        id=record.id,
        ingestion_key=record.ingestion_key,
        payload_digest=record.payload_digest,
        source=record.source,
        data_kind=record.data_kind,
        symbol_id=record.symbol_id,
        instrument_id=record.instrument_id,
        observed_at=stored_utc(record.observed_at),
        ingested_at=stored_utc(record.ingested_at),
        session_date=record.session_date,
        quality_state=record.quality_state,
        configuration_version_id=record.configuration_version_id,
        payload=dict(record.payload),
        payload_schema_version=record.payload_schema_version,
        correlation_id=record.correlation_id,
    )


def _quarantine_to_domain(record: MarketDataQuarantineORM) -> MarketDataQuarantine:
    return MarketDataQuarantine(
        id=record.id,
        ingestion_key=record.ingestion_key,
        source=record.source,
        event_id=record.event_id,
        data_kind=record.data_kind,
        observed_at=stored_utc(record.observed_at),
        ingested_at=stored_utc(record.ingested_at),
        symbol_identity=record.symbol_identity,
        instrument_identity=record.instrument_identity,
        sanitized_payload=dict(record.sanitized_payload),
        payload_digest=record.payload_digest,
        reason_codes=tuple(record.reason_codes),
        fixture_schema_version=record.fixture_schema_version,
        normalized_schema_version=record.normalized_schema_version,
        configuration_version=record.configuration_version,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
    )
