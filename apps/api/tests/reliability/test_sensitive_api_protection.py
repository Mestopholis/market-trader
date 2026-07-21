from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from market_trader.config import get_settings
from market_trader.db.migrations import upgrade_to_head
from market_trader.main import create_app
from market_trader.security.csrf import CSRF_HEADER_NAME
from market_trader.security.passwords import hash_password


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard/overview",
        "/api/paper/orders",
        "/api/market-state",
        "/api/readiness",
    ],
)
def test_sensitive_read_endpoints_reject_unauthenticated_requests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    response = TestClient(create_app(), base_url="https://testserver").get(path)

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"code": "unauthenticated", "summary": "Authentication required."}


def test_health_remains_public_when_auth_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    response = TestClient(create_app(), base_url="https://testserver").get("/api/health")

    assert response.status_code == 200


def test_mutating_paper_endpoint_rejects_unauthenticated_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    response = TestClient(create_app(), base_url="https://testserver").post("/api/paper/recover")

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"code": "unauthenticated", "summary": "Authentication required."}


def test_mutating_paper_endpoint_requires_csrf_for_authenticated_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    client = TestClient(create_app(), base_url="https://testserver")
    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "local-password"},
    )
    assert login.status_code == 200

    response = client.post("/api/paper/recover")

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"code": "csrf_failed", "summary": "CSRF token required."}


def test_mutating_paper_endpoint_accepts_authenticated_csrf_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    client = TestClient(create_app(), base_url="https://testserver")
    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "local-password"},
    )
    csrf_token = client.cookies.get("market_trader_csrf")
    assert login.status_code == 200
    assert csrf_token is not None

    response = client.post("/api/paper/recover", headers={CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["paper_mode"] is True


def _configure_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database = tmp_path / "sensitive.db"
    upgrade_to_head(f"sqlite:///{database}")
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setenv("MARKET_TRADER_AUTH_USERNAME", "operator")
    monkeypatch.setenv(
        "MARKET_TRADER_AUTH_PASSWORD_HASH",
        hash_password("local-password", salt="fixed-salt"),
    )
    monkeypatch.setenv("MARKET_TRADER_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("MARKET_TRADER_SESSION_TTL_SECONDS", "1800")
