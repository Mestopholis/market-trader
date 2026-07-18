from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

from market_trader.db.migrations import alembic_config


def test_initial_migration_creates_domain_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"

    command.upgrade(alembic_config(database_url), "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {
            "symbols",
            "instruments",
            "market_data_snapshots",
            "signals",
            "candidates",
            "proposed_trades",
            "approvals",
            "orders",
            "fills",
            "positions",
            "risk_locks",
            "journal_events",
            "configuration_versions",
        }.issubset(set(inspector.get_table_names()))
    finally:
        engine.dispose()
