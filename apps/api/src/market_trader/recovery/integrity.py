import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel


class IntegrityError(ValueError):
    pass


class IntegrityResult(BaseModel):
    ok: bool
    checks: tuple[str, ...]


def validate_sqlite_integrity(database: Path) -> IntegrityResult:
    if not database.exists():
        raise FileNotFoundError(database)
    with closing(sqlite3.connect(database)) as connection:
        _validate_pragma_integrity(connection)
        _validate_paper_audit_consistency(connection)
    return IntegrityResult(ok=True, checks=("sqlite_integrity", "paper_audit_consistency"))


def _validate_pragma_integrity(connection: sqlite3.Connection) -> None:
    rows = [row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()]
    if rows != ["ok"]:
        raise IntegrityError("sqlite integrity check failed")


def _validate_paper_audit_consistency(connection: sqlite3.Connection) -> None:
    missing = connection.execute(
        """
        SELECT COUNT(*)
        FROM orders AS orders_table
        WHERE NOT EXISTS (
            SELECT 1
            FROM journal_events AS events
            WHERE events.correlation_id = orders_table.correlation_id
        )
        """
    ).fetchone()[0]
    if int(missing) > 0:
        raise IntegrityError("paper orders have missing audit events")
