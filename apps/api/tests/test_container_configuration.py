from pathlib import Path


def test_api_container_runs_migrations_before_startup() -> None:
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()

    assert "COPY alembic.ini ./" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "alembic upgrade head && exec uvicorn" in dockerfile


def test_migrations_use_the_configured_database_url() -> None:
    migration_environment = (
        Path(__file__).resolve().parents[1] / "migrations" / "env.py"
    ).read_text()

    assert 'os.getenv("MARKET_TRADER_DATABASE_URL")' in migration_environment
