from datetime import UTC
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditEventCreate, AuditRepository
from tests.test_migrations import alembic_config


def migrated_engine(tmp_path: Path) -> Engine:
    database_url = f"sqlite:///{tmp_path / 'audit.db'}"
    command.upgrade(alembic_config(database_url), "head")
    return create_engine_from_url(database_url)


def test_appends_and_fetches_journal_event(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            repo = AuditRepository(session)
            event = repo.append(
                AuditEventCreate(
                    correlation_id="corr_1",
                    event_type="symbol.created",
                    actor_type="system",
                    occurred_at=utc_now(),
                    subject_type="symbol",
                    subject_id="sym_1",
                    payload={"schema_version": 1, "symbol": "SPY"},
                    schema_version=1,
                )
            )
            session.commit()

        with Session(engine) as session:
            repo = AuditRepository(session)
            stored = repo.get(event.id)
            by_correlation = repo.list_by_correlation_id("corr_1")
            by_subject = repo.list_by_subject("symbol", "sym_1")

        assert stored == event
        assert [item.id for item in by_correlation] == [event.id]
        assert [item.id for item in by_subject] == [event.id]
        assert stored is not None
        assert stored.occurred_at.tzinfo is UTC
        assert stored.recorded_at.tzinfo is UTC
    finally:
        engine.dispose()


def test_journal_events_reject_direct_update_and_delete(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session:
            event = AuditRepository(session).append(
                AuditEventCreate(
                    correlation_id="corr_2",
                    event_type="symbol.created",
                    actor_type="system",
                    occurred_at=utc_now(),
                    subject_type="symbol",
                    subject_id="sym_2",
                    payload={"schema_version": 1},
                    schema_version=1,
                )
            )
            session.commit()

        with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
            connection.execute(
                text("UPDATE journal_events SET event_type = 'changed' WHERE id = :id"),
                {"id": event.id},
            )

        with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
            connection.execute(
                text("DELETE FROM journal_events WHERE id = :id"),
                {"id": event.id},
            )
    finally:
        engine.dispose()
