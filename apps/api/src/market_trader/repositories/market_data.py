from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import MarketDataSnapshotORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


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


@dataclass(frozen=True)
class MarketDataSnapshot:
    id: str
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


class MarketDataRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def store_snapshot(self, command: MarketDataSnapshotCreate) -> MarketDataSnapshot:
        record = MarketDataSnapshotORM(
            id=new_domain_id("mds"),
            source=command.source,
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
                    "symbol_id": command.symbol_id,
                    "quality_state": command.quality_state,
                },
                schema_version=1,
            )
        )
        return _to_domain(record)

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
        return [_to_domain(record) for record in records]


def _to_domain(record: MarketDataSnapshotORM) -> MarketDataSnapshot:
    return MarketDataSnapshot(
        id=record.id,
        source=record.source,
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
