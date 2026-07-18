from pathlib import Path

from sqlalchemy import text

from market_trader.db.engine import create_engine_from_url
from market_trader.db.session import session_scope


def test_sqlite_engine_enables_foreign_keys(tmp_path: Path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'test.db'}")
    try:
        with engine.connect() as connection:
            enabled = connection.execute(text("PRAGMA foreign_keys")).scalar_one()

        assert enabled == 1
    finally:
        engine.dispose()


def test_session_scope_commits_successful_transaction(tmp_path: Path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'test.db'}")
    try:
        with session_scope(engine) as session:
            session.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)"))
            session.execute(text("INSERT INTO sample (value) VALUES ('ok')"))

        with engine.connect() as connection:
            value = connection.execute(text("SELECT value FROM sample")).scalar_one()

        assert value == "ok"
    finally:
        engine.dispose()
