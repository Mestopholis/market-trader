from __future__ import annotations

from fastapi.testclient import TestClient

from market_trader.config import get_settings
from market_trader.main import create_app
from market_trader.security.csrf import CSRF_HEADER_NAME
from market_trader.security.passwords import hash_password


def test_logout_requires_csrf_token_for_authenticated_session(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure_auth(monkeypatch)
    client = TestClient(create_app(), base_url="https://testserver")
    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "local-password"},
    )
    assert login.status_code == 200

    missing = client.post("/api/auth/logout")

    assert missing.status_code == 403
    assert missing.headers["Cache-Control"] == "no-store"
    assert missing.json() == {"code": "csrf_failed", "summary": "CSRF token required."}


def test_logout_clears_session_when_csrf_header_matches_cookie(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure_auth(monkeypatch)
    client = TestClient(create_app(), base_url="https://testserver")
    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "local-password"},
    )
    csrf_token = client.cookies.get("market_trader_csrf")
    assert login.status_code == 200
    assert csrf_token is not None

    response = client.post("/api/auth/logout", headers={CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == 204
    set_cookie = response.headers.get_list("set-cookie")
    assert any("market_trader_session=""" in cookie for cookie in set_cookie)
    assert any("market_trader_csrf=""" in cookie for cookie in set_cookie)


def _configure_auth(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_TRADER_AUTH_USERNAME", "operator")
    monkeypatch.setenv(
        "MARKET_TRADER_AUTH_PASSWORD_HASH",
        hash_password("local-password", salt="fixed-salt"),
    )
    monkeypatch.setenv("MARKET_TRADER_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("MARKET_TRADER_SESSION_TTL_SECONDS", "1800")
