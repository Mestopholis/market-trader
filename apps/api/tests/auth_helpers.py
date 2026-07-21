from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_trader.config import get_settings
from market_trader.security.passwords import hash_password
from market_trader.security.session import SESSION_COOKIE_NAME, create_session_token

_TEST_USERNAME = "operator"
_TEST_PASSWORD = "local-password"
_TEST_SECRET = "test-session-secret"


def authenticated_client(monkeypatch: pytest.MonkeyPatch, app: FastAPI) -> TestClient:
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_TRADER_AUTH_USERNAME", _TEST_USERNAME)
    monkeypatch.setenv(
        "MARKET_TRADER_AUTH_PASSWORD_HASH",
        hash_password(_TEST_PASSWORD, salt="fixed-salt"),
    )
    monkeypatch.setenv("MARKET_TRADER_SESSION_SECRET", _TEST_SECRET)
    monkeypatch.setenv("MARKET_TRADER_SESSION_TTL_SECONDS", "1800")
    client = TestClient(app)
    client.cookies.set(
        SESSION_COOKIE_NAME,
        create_session_token(
            username=_TEST_USERNAME,
            issued_at=datetime.now(UTC),
            secret=_TEST_SECRET,
        ),
    )
    return client
