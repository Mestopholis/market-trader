from pathlib import Path

from fastapi.testclient import TestClient

from market_trader.api.health import database_state
from market_trader.main import app


def test_health_reports_paper_mode_without_secrets() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "environment": "local",
        "trading_mode": "paper",
        "version": "0.1.0",
        "database": body["database"],
    }
    assert body["database"] in {"ok", "unavailable"}
    assert "database_url" not in response.text
    assert "sqlite:///" not in response.text


def test_database_state_reports_ok_for_reachable_database(tmp_path: Path) -> None:
    assert database_state(f"sqlite:///{tmp_path / 'health.db'}") == "ok"


def test_database_state_reports_unavailable_without_exposing_error(tmp_path: Path) -> None:
    missing_parent = tmp_path / "missing" / "health.db"

    assert database_state(f"sqlite:///{missing_parent}") == "unavailable"
