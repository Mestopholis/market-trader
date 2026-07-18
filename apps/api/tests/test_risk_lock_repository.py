from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.risk_locks import RiskLockCreate, RiskLockRepository
from tests.db_helpers import migrated_engine


def test_creates_fetches_and_clears_risk_lock_with_audit_event(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    activated_at = utc_now()
    try:
        with Session(engine) as session:
            repository = RiskLockRepository(session)
            created = repository.create(
                RiskLockCreate(
                    lock_type="manual_fixture",
                    status="active",
                    reason="fixture only",
                    source_event_id=None,
                    activated_at=activated_at,
                    payload={"schema_version": 1},
                    payload_schema_version=1,
                    correlation_id="corr_lock",
                )
            )
            session.commit()

        with Session(engine) as session:
            active = RiskLockRepository(session).get_active("manual_fixture")
        assert active == created

        cleared_at = utc_now()
        with Session(engine) as session:
            cleared = RiskLockRepository(session).clear(
                created.id,
                cleared_at=cleared_at,
                correlation_id="corr_lock",
            )
            session.commit()

        with Session(engine) as session:
            repository = RiskLockRepository(session)
            no_active_lock = repository.get_active("manual_fixture")
            clearing_event = (
                AuditRepository(session).get(cleared.clearing_event_id)
                if cleared is not None and cleared.clearing_event_id is not None
                else None
            )

        assert cleared is not None
        assert cleared.status == "cleared"
        assert cleared.cleared_at == cleared_at
        assert no_active_lock is None
        assert clearing_event is not None
        assert clearing_event.event_type == "risk_lock.cleared"
    finally:
        engine.dispose()
