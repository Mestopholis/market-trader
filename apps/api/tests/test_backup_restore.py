from datetime import UTC
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.db.backup import backup_sqlite_database, restore_sqlite_database
from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import upgrade_to_head
from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditRepository
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository


def test_sqlite_backup_restore_preserves_domain_record_and_audit_event(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    upgrade_to_head(f"sqlite:///{source}")

    observed_at = utc_now()
    source_engine = create_engine_from_url(f"sqlite:///{source}")
    try:
        with Session(source_engine) as session:
            symbol = SymbolRepository(session).create_symbol(
                SymbolCreate(
                    display_symbol="DIA",
                    instrument_type="equity",
                    exchange=None,
                    is_active=True,
                    first_observed_at=observed_at,
                    last_observed_at=observed_at,
                    metadata_payload={"schema_version": 1, "fixture": True},
                    metadata_schema_version=1,
                    correlation_id="corr_restore",
                )
            )
            session.commit()
    finally:
        source_engine.dispose()

    backup_sqlite_database(source, backup)
    restore_sqlite_database(backup, restored)

    restored_engine = create_engine_from_url(f"sqlite:///{restored}")
    try:
        with Session(restored_engine) as session:
            stored_symbol = SymbolRepository(session).get_symbol_by_display_symbol("DIA")
            events = AuditRepository(session).list_by_correlation_id("corr_restore")

        assert stored_symbol == symbol
        assert stored_symbol is not None
        assert stored_symbol.first_observed_at.tzinfo is UTC
        assert len(events) == 1
        assert events[0].subject_id == stored_symbol.id
    finally:
        restored_engine.dispose()
