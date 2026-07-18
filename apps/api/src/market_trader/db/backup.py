import sqlite3
from contextlib import closing
from pathlib import Path


def backup_sqlite_database(source: Path, destination: Path) -> None:
    _copy_sqlite_database(source, destination)


def restore_sqlite_database(backup: Path, destination: Path) -> None:
    _copy_sqlite_database(backup, destination)


def _copy_sqlite_database(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source)) as source_connection,
        closing(sqlite3.connect(destination)) as destination_connection,
    ):
        source_connection.backup(destination_connection)
