from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import alembic_config


def migrated_engine(tmp_path: Path, filename: str = "test.db") -> Engine:
    database_url = f"sqlite:///{tmp_path / filename}"
    command.upgrade(alembic_config(database_url), "head")
    return create_engine_from_url(database_url)
