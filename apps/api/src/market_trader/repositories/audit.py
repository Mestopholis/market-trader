from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import JournalEventORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now
from market_trader.repositories._mapping import stored_utc


@dataclass(frozen=True)
class AuditEventCreate:
    correlation_id: str
    event_type: str
    actor_type: str
    occurred_at: datetime
    subject_type: str
    subject_id: str
    payload: dict[str, Any]
    schema_version: int
    causation_event_id: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    id: str
    correlation_id: str
    event_type: str
    actor_type: str
    occurred_at: datetime
    recorded_at: datetime
    subject_type: str
    subject_id: str
    payload: dict[str, Any]
    schema_version: int
    causation_event_id: str | None


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: AuditEventCreate) -> AuditEvent:
        record = JournalEventORM(
            id=new_domain_id("evt"),
            correlation_id=event.correlation_id,
            event_type=event.event_type,
            actor_type=event.actor_type,
            occurred_at=ensure_utc(event.occurred_at),
            recorded_at=utc_now(),
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            causation_event_id=event.causation_event_id,
            payload=dict(event.payload),
            schema_version=event.schema_version,
        )
        self._session.add(record)
        self._session.flush()
        return _to_domain(record)

    def get(self, event_id: str) -> AuditEvent | None:
        record = self._session.get(JournalEventORM, event_id)
        return _to_domain(record) if record is not None else None

    def list_by_correlation_id(self, correlation_id: str) -> list[AuditEvent]:
        records = self._session.scalars(
            select(JournalEventORM)
            .where(JournalEventORM.correlation_id == correlation_id)
            .order_by(JournalEventORM.occurred_at, JournalEventORM.id)
        )
        return [_to_domain(record) for record in records]

    def list_by_subject(self, subject_type: str, subject_id: str) -> list[AuditEvent]:
        records = self._session.scalars(
            select(JournalEventORM)
            .where(
                JournalEventORM.subject_type == subject_type,
                JournalEventORM.subject_id == subject_id,
            )
            .order_by(JournalEventORM.occurred_at, JournalEventORM.id)
        )
        return [_to_domain(record) for record in records]


def _to_domain(record: JournalEventORM) -> AuditEvent:
    return AuditEvent(
        id=record.id,
        correlation_id=record.correlation_id,
        event_type=record.event_type,
        actor_type=record.actor_type,
        occurred_at=stored_utc(record.occurred_at),
        recorded_at=stored_utc(record.recorded_at),
        subject_type=record.subject_type,
        subject_id=record.subject_id,
        payload=dict(record.payload),
        schema_version=record.schema_version,
        causation_event_id=record.causation_event_id,
    )
