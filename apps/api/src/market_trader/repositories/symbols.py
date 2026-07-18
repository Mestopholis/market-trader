from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import InstrumentORM, SymbolORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


@dataclass(frozen=True)
class SymbolCreate:
    display_symbol: str
    instrument_type: str
    exchange: str | None
    is_active: bool
    first_observed_at: datetime
    last_observed_at: datetime
    metadata_payload: dict[str, Any]
    metadata_schema_version: int
    correlation_id: str


@dataclass(frozen=True)
class Symbol:
    id: str
    display_symbol: str
    instrument_type: str
    exchange: str | None
    is_active: bool
    first_observed_at: datetime
    last_observed_at: datetime
    metadata_payload: dict[str, Any]
    metadata_schema_version: int
    correlation_id: str


@dataclass(frozen=True)
class InstrumentCreate:
    symbol_id: str
    instrument_type: str
    exchange: str | None
    external_reference: str | None
    is_active: bool
    first_observed_at: datetime
    last_observed_at: datetime
    metadata_payload: dict[str, Any]
    metadata_schema_version: int
    correlation_id: str


@dataclass(frozen=True)
class Instrument:
    id: str
    symbol_id: str
    instrument_type: str
    exchange: str | None
    external_reference: str | None
    is_active: bool
    first_observed_at: datetime
    last_observed_at: datetime
    metadata_payload: dict[str, Any]
    metadata_schema_version: int
    correlation_id: str


class SymbolRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def create_symbol(self, command: SymbolCreate) -> Symbol:
        record = SymbolORM(
            id=new_domain_id("sym"),
            display_symbol=command.display_symbol,
            instrument_type=command.instrument_type,
            exchange=command.exchange,
            is_active=command.is_active,
            first_observed_at=ensure_utc(command.first_observed_at),
            last_observed_at=ensure_utc(command.last_observed_at),
            metadata_payload=dict(command.metadata_payload),
            metadata_schema_version=command.metadata_schema_version,
            correlation_id=command.correlation_id,
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="symbol.created",
                actor_type="system",
                occurred_at=utc_now(),
                subject_type="symbol",
                subject_id=record.id,
                payload={
                    "schema_version": 1,
                    "display_symbol": command.display_symbol,
                },
                schema_version=1,
            )
        )
        return _symbol_to_domain(record)

    def get_symbol_by_display_symbol(self, display_symbol: str) -> Symbol | None:
        record = self._session.scalar(
            select(SymbolORM).where(SymbolORM.display_symbol == display_symbol)
        )
        return _symbol_to_domain(record) if record is not None else None

    def create_instrument(self, command: InstrumentCreate) -> Instrument:
        record = InstrumentORM(
            id=new_domain_id("ins"),
            symbol_id=command.symbol_id,
            instrument_type=command.instrument_type,
            exchange=command.exchange,
            external_reference=command.external_reference,
            is_active=command.is_active,
            first_observed_at=ensure_utc(command.first_observed_at),
            last_observed_at=ensure_utc(command.last_observed_at),
            metadata_payload=dict(command.metadata_payload),
            metadata_schema_version=command.metadata_schema_version,
            correlation_id=command.correlation_id,
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="instrument.created",
                actor_type="system",
                occurred_at=utc_now(),
                subject_type="instrument",
                subject_id=record.id,
                payload={"schema_version": 1, "symbol_id": command.symbol_id},
                schema_version=1,
            )
        )
        return _instrument_to_domain(record)

    def get_instruments_for_symbol(self, symbol_id: str) -> list[Instrument]:
        records = self._session.scalars(
            select(InstrumentORM)
            .where(InstrumentORM.symbol_id == symbol_id)
            .order_by(InstrumentORM.id)
        )
        return [_instrument_to_domain(record) for record in records]


def _symbol_to_domain(record: SymbolORM) -> Symbol:
    return Symbol(
        id=record.id,
        display_symbol=record.display_symbol,
        instrument_type=record.instrument_type,
        exchange=record.exchange,
        is_active=record.is_active,
        first_observed_at=stored_utc(record.first_observed_at),
        last_observed_at=stored_utc(record.last_observed_at),
        metadata_payload=dict(record.metadata_payload),
        metadata_schema_version=record.metadata_schema_version,
        correlation_id=record.correlation_id,
    )


def _instrument_to_domain(record: InstrumentORM) -> Instrument:
    return Instrument(
        id=record.id,
        symbol_id=record.symbol_id,
        instrument_type=record.instrument_type,
        exchange=record.exchange,
        external_reference=record.external_reference,
        is_active=record.is_active,
        first_observed_at=stored_utc(record.first_observed_at),
        last_observed_at=stored_utc(record.last_observed_at),
        metadata_payload=dict(record.metadata_payload),
        metadata_schema_version=record.metadata_schema_version,
        correlation_id=record.correlation_id,
    )
