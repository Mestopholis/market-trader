from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from market_trader.db.backup import restore_sqlite_database
from market_trader.db.engine import create_engine_from_url
from market_trader.domain.time import Clock, SystemClock, ensure_utc
from market_trader.recovery.backup import TRACKED_BACKUP_TABLES, BackupMetadata, file_sha256
from market_trader.recovery.integrity import validate_sqlite_integrity
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


class RestoreValidationError(ValueError):
    pass


class RestoreValidationReport(BaseModel):
    correlation_id: str
    validated_at: datetime
    source_backup_path: str
    restored_database_path: str
    backup_sha256: str
    row_counts: dict[str, int]
    integrity_ok: bool
    recovery_event_id: str


def restore_backup_with_validation(
    backup: Path,
    destination: Path,
    *,
    expected_metadata: BackupMetadata,
    correlation_id: str,
    force: bool = False,
    clock: Clock | None = None,
) -> RestoreValidationReport:
    active_clock = clock or SystemClock()
    backup_sha256 = file_sha256(backup)
    if backup_sha256 != expected_metadata.sha256:
        raise RestoreValidationError("backup checksum mismatch")

    restore_sqlite_database(backup, destination, force=force)
    integrity = validate_sqlite_integrity(destination)
    restored_counts = _row_counts(destination)
    _validate_expected_counts(restored_counts, expected_metadata.row_counts)

    event_id = _append_restore_event(
        destination,
        correlation_id=correlation_id,
        occurred_at=active_clock.now(),
        backup_sha256=backup_sha256,
        row_counts={**restored_counts, "journal_events": restored_counts["journal_events"] + 1},
    )
    final_counts = _row_counts(destination)
    return RestoreValidationReport(
        correlation_id=correlation_id,
        validated_at=ensure_utc(active_clock.now()),
        source_backup_path=str(backup),
        restored_database_path=str(destination),
        backup_sha256=backup_sha256,
        row_counts=final_counts,
        integrity_ok=integrity.ok,
        recovery_event_id=event_id,
    )


def _validate_expected_counts(
    restored_counts: dict[str, int],
    expected_counts: dict[str, int],
) -> None:
    mismatches = {
        table: {"expected": expected_counts.get(table), "actual": restored_counts[table]}
        for table in TRACKED_BACKUP_TABLES
        if restored_counts[table] != expected_counts.get(table)
    }
    if mismatches:
        raise RestoreValidationError(f"restored row counts mismatch: {mismatches}")


def _append_restore_event(
    database: Path,
    *,
    correlation_id: str,
    occurred_at: datetime,
    backup_sha256: str,
    row_counts: dict[str, int],
) -> str:
    engine = create_engine_from_url(f"sqlite:///{database}")
    try:
        with Session(engine) as session:
            event = AuditRepository(session).append(
                AuditEventCreate(
                    correlation_id=correlation_id,
                    event_type="recovery.restore_validated",
                    actor_type="system",
                    occurred_at=occurred_at,
                    subject_type="database",
                    subject_id=str(database),
                    payload={
                        "schema_version": 1,
                        "backup_sha256": backup_sha256,
                        "row_counts": row_counts,
                        "validated_tables": list(TRACKED_BACKUP_TABLES),
                    },
                    schema_version=1,
                )
            )
            session.commit()
            return event.id
    finally:
        engine.dispose()


def _row_counts(database: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database)) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in TRACKED_BACKUP_TABLES
        }

