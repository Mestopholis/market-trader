from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import ConfigurationVersionORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


@dataclass(frozen=True)
class ConfigurationVersionCreate:
    configuration_key: str
    version: str
    effective_at: datetime
    retired_at: datetime | None
    content_hash: str
    payload: dict[str, Any]
    schema_version: int
    correlation_id: str


@dataclass(frozen=True)
class ConfigurationVersion:
    id: str
    configuration_key: str
    version: str
    effective_at: datetime
    retired_at: datetime | None
    content_hash: str
    payload: dict[str, Any]
    schema_version: int
    creation_event_id: str
    correlation_id: str
    created_at: datetime


class ConfigurationVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def create(self, command: ConfigurationVersionCreate) -> ConfigurationVersion:
        record_id = new_domain_id("cfg")
        created_at = utc_now()
        event = self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="configuration_version.created",
                actor_type="system",
                occurred_at=created_at,
                subject_type="configuration_version",
                subject_id=record_id,
                payload={
                    "schema_version": 1,
                    "configuration_key": command.configuration_key,
                    "version": command.version,
                    "content_hash": command.content_hash,
                },
                schema_version=1,
            )
        )
        record = ConfigurationVersionORM(
            id=record_id,
            configuration_key=command.configuration_key,
            version=command.version,
            effective_at=ensure_utc(command.effective_at),
            retired_at=ensure_utc(command.retired_at) if command.retired_at is not None else None,
            content_hash=command.content_hash,
            payload=dict(command.payload),
            schema_version=command.schema_version,
            creation_event_id=event.id,
            correlation_id=command.correlation_id,
            created_at=created_at,
        )
        self._session.add(record)
        self._session.flush()
        return _to_domain(record)

    def get_active_by_key(
        self, configuration_key: str, *, as_of: datetime | None = None
    ) -> ConfigurationVersion | None:
        effective_at = ensure_utc(as_of) if as_of is not None else utc_now()
        record = self._session.scalar(
            select(ConfigurationVersionORM)
            .where(
                ConfigurationVersionORM.configuration_key == configuration_key,
                ConfigurationVersionORM.effective_at <= effective_at,
                ConfigurationVersionORM.retired_at.is_(None),
            )
            .order_by(ConfigurationVersionORM.effective_at.desc())
            .limit(1)
        )
        return _to_domain(record) if record is not None else None


def _to_domain(record: ConfigurationVersionORM) -> ConfigurationVersion:
    return ConfigurationVersion(
        id=record.id,
        configuration_key=record.configuration_key,
        version=record.version,
        effective_at=stored_utc(record.effective_at),
        retired_at=stored_utc(record.retired_at) if record.retired_at is not None else None,
        content_hash=record.content_hash,
        payload=dict(record.payload),
        schema_version=record.schema_version,
        creation_event_id=record.creation_event_id,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
    )
