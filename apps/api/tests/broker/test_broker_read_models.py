from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from market_trader.api.auth import require_authenticated_session
from market_trader.broker.read_models import SchwabBrokerStatus, SchwabBrokerStatusReader
from market_trader.broker.schwab.oauth import SCHWAB_MARKET_DATA_TOKEN_ID
from market_trader.broker.schwab.tokens import (
    SchwabTokenBundle,
    SchwabTokenCipher,
    SchwabTokenRepository,
)
from market_trader.config import get_settings
from market_trader.db.engine import create_engine_from_url
from market_trader.db.migrations import alembic_config
from market_trader.db.models import SchwabMarketDataSyncORM
from market_trader.main import create_app
from market_trader.security.session import SessionClaims

NOW = datetime(2026, 7, 28, 14, 0, tzinfo=UTC)
KEY = "local-token-encryption-key"


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_status_reports_configured_but_disconnected(tmp_path: Path) -> None:
    database_url = _migrated_database(tmp_path)

    status = _read_status(database_url)

    assert status.configured is True
    assert status.connection_state == "disconnected"
    assert status.market_data_state == "unknown"
    assert status.token is None
    assert status.actions == {
        "oauth_start": True,
        "refresh": False,
        "revoke": False,
    }


def test_status_reports_active_token_and_latest_market_data_sync(tmp_path: Path) -> None:
    database_url = _migrated_database(tmp_path)
    _store_token(database_url, expires_at=NOW + timedelta(minutes=30))
    _store_sync(database_url, provider_state="available", observed_at=NOW - timedelta(minutes=2))

    status = _read_status(database_url)

    assert status.connection_state == "connected"
    assert status.market_data_state == "available"
    assert status.token is not None
    assert status.token.is_expired is False
    assert status.last_market_data_refresh is not None
    assert status.last_market_data_refresh.provider_state == "available"
    assert status.last_market_data_refresh.is_stale is False
    assert status.actions["refresh"] is True
    assert status.actions["revoke"] is True


def test_status_reports_expired_revoked_rate_limited_and_stale(tmp_path: Path) -> None:
    database_url = _migrated_database(tmp_path)
    _store_token(database_url, expires_at=NOW - timedelta(seconds=1), revoked=True)
    _store_sync(
        database_url,
        provider_state="rate_limited",
        observed_at=NOW - timedelta(minutes=45),
    )

    status = _read_status(database_url)

    assert status.connection_state == "revoked"
    assert status.market_data_state == "rate_limited"
    assert status.token is not None
    assert status.token.status == "revoked"
    assert status.token.is_expired is True
    assert status.last_market_data_refresh is not None
    assert status.last_market_data_refresh.is_stale is True
    assert status.actions["refresh"] is False
    assert status.actions["revoke"] is False


def test_broker_status_api_requires_auth_and_returns_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _migrated_database(tmp_path)
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", database_url)
    _set_schwab_env(monkeypatch)
    get_settings.cache_clear()

    app = create_app()
    unauthenticated = TestClient(app).get("/api/broker/schwab/status")
    assert unauthenticated.status_code == 401

    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=NOW,
    )
    response = TestClient(app).get("/api/broker/schwab/status")

    assert response.status_code == 200
    assert response.json()["connection_state"] == "disconnected"
    assert "client_secret" not in response.text
    assert "access_token" not in response.text


def test_readiness_includes_schwab_components_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _migrated_database(tmp_path)
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", database_url)
    _set_schwab_env(monkeypatch)
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=NOW,
    )

    response = TestClient(app).get("/api/readiness")

    assert response.status_code == 200
    components = {component["name"]: component for component in response.json()["components"]}
    assert components["schwab_auth"]["status"] == "warning"
    assert components["schwab_auth"]["code"] == "schwab_disconnected"
    assert components["schwab_market_data"]["status"] == "unknown"
    assert components["schwab_market_data"]["code"] == "schwab_market_data_unknown"


def _read_status(database_url: str) -> SchwabBrokerStatus:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session:
            return SchwabBrokerStatusReader(
                session=session,
                token_key=KEY,
                now=NOW,
            ).read()
    finally:
        engine.dispose()


def _migrated_database(tmp_path: Path) -> str:
    database_url = f"sqlite:///{tmp_path / 'broker-status.db'}"
    command.upgrade(alembic_config(database_url), "head")
    return database_url


def _set_schwab_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_MARKET_DATA_ENABLED", "true")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_ID", "client-id")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY", KEY)


def _store_token(database_url: str, *, expires_at: datetime, revoked: bool = False) -> None:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session, session.begin():
            repository = SchwabTokenRepository(SchwabTokenCipher(KEY))
            repository.store_initial(
                session,
                token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
                product="market_data",
                bundle=SchwabTokenBundle(
                    access_token="synthetic-access-token",
                    refresh_token="synthetic-refresh-token",
                    token_type="Bearer",
                    scope="api",
                    access_token_expires_at=expires_at,
                    refresh_token_expires_at=None,
                ),
                now=NOW,
                correlation_id="corr-status-token",
            )
            if revoked:
                repository.revoke(
                    session,
                    token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
                    now=NOW,
                    reason_code="operator_revoked",
                )
    finally:
        engine.dispose()


def _store_sync(database_url: str, *, provider_state: str, observed_at: datetime) -> None:
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session, session.begin():
            session.add(
                SchwabMarketDataSyncORM(
                    id="sync-status",
                    sync_key="manual-status",
                    data_kind="quote",
                    status="completed",
                    provider_state=provider_state,
                    observed_at=observed_at,
                    completed_at=observed_at + timedelta(seconds=1),
                    payload={"schema_version": 1},
                    correlation_id="corr-status-sync",
                    created_at=observed_at,
                )
            )
    finally:
        engine.dispose()
