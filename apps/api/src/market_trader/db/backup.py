import sqlite3
from contextlib import closing
from pathlib import Path

from market_trader.recovery.backup import BackupMetadata, collect_backup_metadata


def backup_sqlite_database(
    source: Path,
    destination: Path,
    *,
    correlation_id: str = "corr-backup",
    force: bool = False,
) -> BackupMetadata:
    if destination.exists() and not force:
        raise FileExistsError(destination)
    metadata = collect_backup_metadata(
        source=source,
        destination=destination,
        correlation_id=correlation_id,
    )
    _copy_sqlite_database(source, destination, force=force)
    return metadata


def restore_sqlite_database(backup: Path, destination: Path, *, force: bool = False) -> None:
    if destination.exists() and not force:
        raise FileExistsError(destination)
    _copy_sqlite_database(backup, destination, force=force)


def _copy_sqlite_database(source: Path, destination: Path, *, force: bool) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    if destination.exists() and force:
        destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source)) as source_connection,
        closing(sqlite3.connect(destination)) as destination_connection,
    ):
        source_connection.backup(destination_connection)
