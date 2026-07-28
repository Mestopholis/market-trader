from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.api.auth import require_authenticated_session, require_csrf_protection
from market_trader.broker.schwab.oauth import (
    SCHWAB_MARKET_DATA_TOKEN_ID,
    SchwabOAuthConfig,
    SchwabOAuthError,
    SchwabOAuthService,
)
from market_trader.broker.schwab.tokens import SchwabTokenCipher, SchwabTokenRepository
from market_trader.config import get_settings
from market_trader.db.base import Base
from market_trader.db.engine import create_engine_from_url
from market_trader.db.models import JournalEventORM, SchwabOAuthStateORM
from market_trader.domain.time import FrozenClock
from market_trader.main import app, create_app
from market_trader.security.csrf import CSRF_HEADER_NAME
from market_trader.security.passwords import hash_password
from market_trader.security.session import SessionClaims

NOW = datetime(2026, 7, 27, 15, 0, tzinfo=UTC)


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'schwab-oauth.db'}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db_session:
            yield db_session
    finally:
        engine.dispose()


@pytest.fixture()
def service() -> Iterator[SchwabOAuthService]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        form = dict(parse_qs(request.content.decode("utf-8")))
        grant_type = form["grant_type"][0]
        if grant_type == "authorization_code":
            assert form["code"] == ["oauth-code-a"]
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token-a",
                    "refresh_token": "refresh-token-a",
                    "token_type": "Bearer",
                    "scope": "api",
                    "expires_in": 1800,
                    "refresh_token_expires_in": 604800,
                },
            )
        if grant_type == "refresh_token":
            assert form["refresh_token"] == ["refresh-token-a"]
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token-b",
                    "refresh_token": "refresh-token-b",
                    "token_type": "Bearer",
                    "scope": "api",
                    "expires_in": 1800,
                    "refresh_token_expires_in": 604800,
                },
            )
        raise AssertionError(f"unexpected grant type: {grant_type}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        oauth = SchwabOAuthService(
            config=_config(),
            token_repository=SchwabTokenRepository(SchwabTokenCipher("local-key")),
            http_client=http_client,
            clock=FrozenClock(NOW),
        )
        oauth.requests = requests  # type: ignore[attr-defined]
        yield oauth


@pytest.fixture(autouse=True)
def clear_app_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_start_creates_authorization_url_and_stores_signed_state(
    session: Session,
    service: SchwabOAuthService,
) -> None:
    started = service.start(session, correlation_id="corr-start")

    parsed = urlparse(started.authorization_url)
    query = parse_qs(parsed.query)
    state_row = session.scalar(select(SchwabOAuthStateORM))

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.schwabapi.com"
    assert parsed.path == "/v1/oauth/authorize"
    assert query["client_id"] == ["client-id-a"]
    assert query["redirect_uri"] == ["https://127.0.0.1:8182"]
    assert query["response_type"] == ["code"]
    assert query["state"] == [started.state]
    assert started.expires_at == NOW + timedelta(minutes=10)
    assert state_row is not None
    assert state_row.status == "pending"
    assert state_row.state_hash != started.state
    assert started.state not in repr(state_row)


def test_callback_rejects_expired_state_without_token_request(
    session: Session,
    service: SchwabOAuthService,
) -> None:
    started = service.start(session, correlation_id="corr-expired")
    expired_service = service.with_clock(FrozenClock(NOW + timedelta(minutes=11)))

    with pytest.raises(SchwabOAuthError, match="oauth_state_expired"):
        expired_service.complete_callback(
            session,
            code="oauth-code-a",
            state=started.state,
            correlation_id="corr-expired",
        )

    assert service.requests == []  # type: ignore[attr-defined]


def test_callback_success_consumes_state_stores_tokens_and_audits(
    session: Session,
    service: SchwabOAuthService,
) -> None:
    started = service.start(session, correlation_id="corr-success")

    metadata = service.complete_callback(
        session,
        code="oauth-code-a",
        state=started.state,
        correlation_id="corr-success",
    )

    state_row = session.scalar(select(SchwabOAuthStateORM))
    events = session.scalars(
        select(JournalEventORM).where(JournalEventORM.correlation_id == "corr-success")
    ).all()
    assert metadata.token_id == SCHWAB_MARKET_DATA_TOKEN_ID
    assert metadata.status == "active"
    assert metadata.access_token_expires_at == NOW + timedelta(seconds=1800)
    assert state_row is not None
    assert state_row.status == "consumed"
    assert state_row.consumed_at == NOW.replace(tzinfo=None)
    assert [event.event_type for event in events] == [
        "schwab.oauth.start",
        "schwab.oauth.callback_succeeded",
    ]


def test_callback_rejects_replay_and_wrong_state(
    session: Session,
    service: SchwabOAuthService,
) -> None:
    started = service.start(session, correlation_id="corr-replay")
    service.complete_callback(
        session,
        code="oauth-code-a",
        state=started.state,
        correlation_id="corr-replay",
    )

    with pytest.raises(SchwabOAuthError, match="oauth_state_replay"):
        service.complete_callback(
            session,
            code="oauth-code-a",
            state=started.state,
            correlation_id="corr-replay",
        )
    with pytest.raises(SchwabOAuthError, match="oauth_state_invalid"):
        service.complete_callback(
            session,
            code="oauth-code-a",
            state="wrong-state",
            correlation_id="corr-wrong-state",
        )


def test_error_callback_records_failure_without_token_request(
    session: Session,
    service: SchwabOAuthService,
) -> None:
    started = service.start(session, correlation_id="corr-error")

    with pytest.raises(SchwabOAuthError, match="oauth_callback_error"):
        service.complete_callback(
            session,
            state=started.state,
            error="access_denied",
            error_description="operator denied",
            correlation_id="corr-error",
        )

    state_row = session.scalar(select(SchwabOAuthStateORM))
    assert state_row is not None
    assert state_row.status == "failed"
    assert service.requests == []  # type: ignore[attr-defined]


def test_refresh_rotates_tokens_and_revoke_blocks_reads(
    session: Session,
    service: SchwabOAuthService,
) -> None:
    started = service.start(session, correlation_id="corr-refresh")
    service.complete_callback(
        session,
        code="oauth-code-a",
        state=started.state,
        correlation_id="corr-refresh",
    )

    refreshed = service.refresh(session, correlation_id="corr-refresh")
    revoked = service.revoke(session, correlation_id="corr-refresh", reason_code="operator_revoked")

    assert refreshed.refreshed_at == NOW
    assert revoked.status == "revoked"
    with pytest.raises(LookupError, match="not active"):
        service.token_repository.read(session, token_id=SCHWAB_MARKET_DATA_TOKEN_ID)


def test_broker_routes_require_auth_and_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    client = TestClient(create_app(), base_url="https://testserver")

    unauthenticated = client.post("/api/broker/schwab/oauth/start")

    assert unauthenticated.status_code == 401

    monkeypatch.setenv("MARKET_TRADER_AUTH_USERNAME", "operator")
    monkeypatch.setenv(
        "MARKET_TRADER_AUTH_PASSWORD_HASH",
        hash_password("local-password", salt="fixed-salt"),
    )
    monkeypatch.setenv("MARKET_TRADER_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("MARKET_TRADER_SESSION_TTL_SECONDS", "1800")
    get_settings.cache_clear()
    csrf_client = TestClient(create_app(), base_url="https://testserver")
    login = csrf_client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "local-password"},
    )
    csrf_missing = csrf_client.post("/api/broker/schwab/oauth/start")

    assert login.status_code == 200
    assert csrf_missing.status_code == 403


def test_broker_routes_start_refresh_and_revoke_with_local_csrf() -> None:
    fake = FakeOAuthService()
    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=NOW,
    )
    app.dependency_overrides[require_csrf_protection] = lambda: None
    from market_trader.api.broker import get_schwab_oauth_service

    app.dependency_overrides[get_schwab_oauth_service] = lambda: fake
    client = TestClient(app, base_url="https://testserver")

    started = client.post("/api/broker/schwab/oauth/start", headers={CSRF_HEADER_NAME: "csrf"})
    refreshed = client.post("/api/broker/schwab/oauth/refresh", headers={CSRF_HEADER_NAME: "csrf"})
    revoked = client.post("/api/broker/schwab/oauth/revoke", headers={CSRF_HEADER_NAME: "csrf"})

    assert started.status_code == 200
    assert started.headers["Cache-Control"] == "no-store"
    assert started.json()["authorization_url"] == "https://api.schwabapi.com/v1/oauth/authorize"
    assert refreshed.json()["status"] == "active"
    assert revoked.json()["status"] == "revoked"
    assert fake.calls == ["start", "refresh", "revoke"]


class FakeOAuthService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self, _session: Session, *, correlation_id: str) -> dict[str, Any]:
        self.calls.append("start")
        return {
            "authorization_url": "https://api.schwabapi.com/v1/oauth/authorize",
            "expires_at": NOW,
            "state": "redacted-to-operator",
        }

    def refresh(self, _session: Session, *, correlation_id: str) -> dict[str, Any]:
        self.calls.append("refresh")
        return {"token_id": SCHWAB_MARKET_DATA_TOKEN_ID, "status": "active"}

    def revoke(
        self,
        _session: Session,
        *,
        correlation_id: str,
        reason_code: str,
    ) -> dict[str, Any]:
        self.calls.append("revoke")
        return {"token_id": SCHWAB_MARKET_DATA_TOKEN_ID, "status": "revoked"}


def _config() -> SchwabOAuthConfig:
    return SchwabOAuthConfig(
        client_id="client-id-a",
        client_secret="client-secret-a",
        callback_url="https://127.0.0.1:8182",
        state_signing_key="local-state-key",
    )
