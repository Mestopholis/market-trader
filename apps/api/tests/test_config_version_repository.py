from datetime import UTC, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.config_versions import (
    ConfigurationVersionCreate,
    ConfigurationVersionRepository,
)
from tests.db_helpers import migrated_engine


def test_creates_and_fetches_active_configuration_version(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    effective_at = utc_now()
    try:
        with Session(engine) as session:
            created = ConfigurationVersionRepository(session).create(
                ConfigurationVersionCreate(
                    configuration_key="scanner.default",
                    version="1.0.0",
                    effective_at=effective_at,
                    retired_at=None,
                    content_hash="sha256:fixture",
                    payload={"schema_version": 1, "minimum_score": 80},
                    schema_version=1,
                    correlation_id="corr_config",
                )
            )
            session.commit()

        with Session(engine) as session:
            stored = ConfigurationVersionRepository(session).get_active_by_key(
                "scanner.default", as_of=effective_at
            )
            event = AuditRepository(session).get(created.creation_event_id)

        assert stored == created
        assert stored is not None
        assert stored.effective_at.tzinfo is UTC
        assert event is not None
        assert event.event_type == "configuration_version.created"
        assert event.correlation_id == "corr_config"
    finally:
        engine.dispose()


def test_configuration_is_active_before_its_retirement_time(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    effective_at = utc_now()
    try:
        with Session(engine) as session:
            created = ConfigurationVersionRepository(session).create(
                ConfigurationVersionCreate(
                    configuration_key="risk.default",
                    version="1.0.0",
                    effective_at=effective_at,
                    retired_at=effective_at + timedelta(days=1),
                    content_hash="sha256:retiring-fixture",
                    payload={"schema_version": 1},
                    schema_version=1,
                    correlation_id="corr_retiring_config",
                )
            )
            session.commit()

        with Session(engine) as session:
            stored = ConfigurationVersionRepository(session).get_active_by_key(
                "risk.default", as_of=effective_at + timedelta(hours=1)
            )

        assert stored == created
    finally:
        engine.dispose()
