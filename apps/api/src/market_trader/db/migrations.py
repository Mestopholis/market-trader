from pathlib import Path

from alembic import command
from alembic.config import Config

_API_ROOT = Path(__file__).resolve().parents[3]


def alembic_config(database_url: str) -> Config:
    api_root = _resolve_api_root()
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


def _resolve_api_root() -> Path:
    for candidate in (_API_ROOT, Path.cwd(), *Path.cwd().parents):
        if (candidate / "alembic.ini").is_file() and (candidate / "migrations").is_dir():
            return candidate
    return _API_ROOT
