from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import RiskLockORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


@dataclass(frozen=True)
class RiskLockCreate:
    lock_type: str
    status: str
    reason: str
    source_event_id: str | None
    activated_at: datetime
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str


@dataclass(frozen=True)
class RiskLock:
    id: str
    lock_type: str
    status: str
    reason: str
    source_event_id: str | None
    activated_at: datetime
    cleared_at: datetime | None
    clearing_event_id: str | None
    payload: dict[str, Any]
    payload_schema_version: int
    correlation_id: str


class RiskLockRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def create(self, command: RiskLockCreate) -> RiskLock:
        record = RiskLockORM(
            id=new_domain_id("rsk"),
            lock_type=command.lock_type,
            status=command.status,
            reason=command.reason,
            source_event_id=command.source_event_id,
            activated_at=ensure_utc(command.activated_at),
            cleared_at=None,
            clearing_event_id=None,
            payload=dict(command.payload),
            payload_schema_version=command.payload_schema_version,
            correlation_id=command.correlation_id,
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="risk_lock.created",
                actor_type="system",
                occurred_at=command.activated_at,
                subject_type="risk_lock",
                subject_id=record.id,
                causation_event_id=command.source_event_id,
                payload={
                    "schema_version": 1,
                    "lock_type": command.lock_type,
                    "reason": command.reason,
                },
                schema_version=1,
            )
        )
        return _to_domain(record)

    def clear(
        self,
        risk_lock_id: str,
        *,
        cleared_at: datetime,
        correlation_id: str,
    ) -> RiskLock | None:
        record = self._session.get(RiskLockORM, risk_lock_id)
        if record is None:
            return None
        event = self._audit.append(
            AuditEventCreate(
                correlation_id=correlation_id,
                event_type="risk_lock.cleared",
                actor_type="system",
                occurred_at=cleared_at,
                subject_type="risk_lock",
                subject_id=record.id,
                causation_event_id=record.source_event_id,
                payload={"schema_version": 1, "lock_type": record.lock_type},
                schema_version=1,
            )
        )
        record.status = "cleared"
        record.cleared_at = ensure_utc(cleared_at)
        record.clearing_event_id = event.id
        self._session.flush()
        return _to_domain(record)

    def get_active(self, lock_type: str) -> RiskLock | None:
        record = self._session.scalar(
            select(RiskLockORM)
            .where(RiskLockORM.lock_type == lock_type, RiskLockORM.status == "active")
            .order_by(RiskLockORM.activated_at.desc())
            .limit(1)
        )
        return _to_domain(record) if record is not None else None


def _to_domain(record: RiskLockORM) -> RiskLock:
    return RiskLock(
        id=record.id,
        lock_type=record.lock_type,
        status=record.status,
        reason=record.reason,
        source_event_id=record.source_event_id,
        activated_at=stored_utc(record.activated_at),
        cleared_at=stored_utc(record.cleared_at) if record.cleared_at is not None else None,
        clearing_event_id=record.clearing_event_id,
        payload=dict(record.payload),
        payload_schema_version=record.payload_schema_version,
        correlation_id=record.correlation_id,
    )
