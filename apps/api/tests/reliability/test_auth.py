from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from market_trader.config import get_settings
from market_trader.main import create_app
from market_trader.security.passwords import hash_password, verify_password
from market_trader.security.session import SESSION_COOKIE_NAME, create_session_token


def test_password_hash_verification_accepts_only_matching_password() -> None:
    password_hash = hash_password("correct horse battery staple", salt="fixed-salt")

    assert verify_password("correct horse battery staple", password_hash) is True
    assert verify_password("wrong password", password_hash) is False
    assert "correct horse" not in password_hash


def test_login_sets_secure_session_and_csrf_cookies(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure_auth(monkeypatch)
    client = TestClient(create_app(), base_url="https://testserver")

    response = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "local-password"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"authenticated": True, "username": "operator"}
    set_cookie = response.headers.get_list("set-cookie")
    assert any("market_trader_session=" in cookie for cookie in set_cookie)
    assert any("HttpOnly" in cookie for cookie in set_cookie)
    assert any("SameSite=strict" in cookie for cookie in set_cookie)
    assert any("Secure" in cookie for cookie in set_cookie)
    assert client.cookies.get("market_trader_csrf")


def test_login_rejects_bad_credentials_without_leaking_configuration(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure_auth(monkeypatch)
    response = TestClient(create_app(), base_url="https://testserver").post(
        "/api/auth/login",
        json={"username": "operator", "password": "bad"},
    )

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"code": "unauthenticated", "summary": "Authentication required."}
    assert "local-password" not in response.text
    assert "pbkdf2" not in response.text


def test_session_endpoint_rejects_expired_session_without_secret_leak(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure_auth(monkeypatch)
    expired = create_session_token(
        username="operator",
        issued_at=datetime.now(UTC) - timedelta(hours=2),
        secret="test-session-secret",
    )
    client = TestClient(create_app(), base_url="https://testserver")
    client.cookies.set(SESSION_COOKIE_NAME, expired)

    response = client.get("/api/auth/session")

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"code": "unauthenticated", "summary": "Authentication required."}
    assert "test-session-secret" not in response.text


def test_health_remains_unauthenticated(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure_auth(monkeypatch)

    response = TestClient(create_app(), base_url="https://testserver").get("/api/health")

    assert response.status_code == 200


def _configure_auth(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_TRADER_AUTH_USERNAME", "operator")
    monkeypatch.setenv(
        "MARKET_TRADER_AUTH_PASSWORD_HASH",
        hash_password("local-password", salt="fixed-salt"),
    )
    monkeypatch.setenv("MARKET_TRADER_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("MARKET_TRADER_SESSION_TTL_SECONDS", "1800")
