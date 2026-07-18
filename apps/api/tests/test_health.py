from fastapi.testclient import TestClient

from market_trader.main import app


def test_health_reports_paper_mode_without_secrets() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "local",
        "trading_mode": "paper",
        "version": "0.1.0",
    }
    assert "database_url" not in response.text
