from pathlib import Path


def test_api_container_runs_migrations_before_startup() -> None:
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()

    assert "COPY alembic.ini ./" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "alembic upgrade head && exec uvicorn" in dockerfile
