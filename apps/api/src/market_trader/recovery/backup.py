import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from market_trader.recovery.integrity import validate_sqlite_integrity

_TRACKED_TABLES = (
    "journal_events",
    "proposed_trades",
    "approvals",
    "orders",
    "fills",
    "positions",
    "risk_locks",
)


class BackupMetadata(BaseModel):
    source_path: str
    destination_path: str
    created_at: datetime
    schema_revision: str
    row_counts: dict[str, int]
    sha256: str
    correlation_id: str
    integrity_ok: bool


def collect_backup_metadata(
    *,
    source: Path,
    destination: Path,
    correlation_id: str,
) -> BackupMetadata:
    integrity = validate_sqlite_integrity(source)
    return BackupMetadata(
        source_path=str(source),
        destination_path=str(destination),
        created_at=datetime.now(UTC),
        schema_revision=_schema_revision(source),
        row_counts=_row_counts(source),
        sha256=_sha256(source),
        correlation_id=correlation_id,
        integrity_ok=integrity.ok,
    )


def _schema_revision(database: Path) -> str:
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return str(row[0]) if row is not None else "none"


def _row_counts(database: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database)) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _TRACKED_TABLES
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
