from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from market_trader.broker.schwab.client import (
    SchwabClientError,
    SchwabClientState,
    SchwabReadOnlyClient,
)
from market_trader.broker.schwab.oauth import SCHWAB_MARKET_DATA_TOKEN_ID
from market_trader.broker.schwab.tokens import (
    SchwabTokenBundle,
    SchwabTokenCipher,
    SchwabTokenRepository,
)
from market_trader.db.base import Base
from market_trader.db.engine import create_engine_from_url
from market_trader.domain.time import FrozenClock

NOW = datetime(2026, 7, 27, 16, 0, tzinfo=UTC)


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'schwab-client.db'}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db_session:
            yield db_session
    finally:
        engine.dispose()


def test_client_injects_bearer_token_and_returns_json(session: Session) -> None:
    repository = _store_token(session, access_token="access-token-a")
    observed_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"ok": True})

    client = _client(repository, httpx.MockTransport(handler))

    payload = client.get_json(session, "/marketdata/v1/quotes", correlation_id="corr-client")

    assert payload == {"ok": True}
    assert observed_headers == ["Bearer access-token-a"]


def test_client_refreshes_expiring_token_before_request(session: Session) -> None:
    repository = _store_token(
        session,
        access_token="access-token-old",
        expires_at=NOW + timedelta(seconds=30),
    )
    refreshed = False
    observed_headers: list[str | None] = []

    def refresh(db_session: Session, correlation_id: str) -> None:
        nonlocal refreshed
        refreshed = True
        repository.rotate(
            db_session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            bundle=_bundle("access-token-new", "refresh-token-new"),
            now=NOW,
        )

    def handler(request: httpx.Request) -> httpx.Response:
        observed_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"ok": True})

    client = _client(repository, httpx.MockTransport(handler), refresh_tokens=refresh)

    client.get_json(session, "/marketdata/v1/quotes", correlation_id="corr-client")

    assert refreshed is True
    assert observed_headers == ["Bearer access-token-new"]


def test_client_revokes_on_unauthorized_response(session: Session) -> None:
    repository = _store_token(session)
    client = _client(repository, httpx.MockTransport(lambda _request: httpx.Response(401)))

    with pytest.raises(SchwabClientError, match="schwab_auth_locked") as error:
        client.get_json(session, "/marketdata/v1/quotes", correlation_id="corr-client")

    metadata = repository.metadata(session, token_id=SCHWAB_MARKET_DATA_TOKEN_ID, now=NOW)
    assert metadata.status == "revoked"
    assert error.value.state is SchwabClientState.AUTH_LOCKED


def test_client_reports_rate_limit_provider_unavailable_and_timeout(
    session: Session,
) -> None:
    repository = _store_token(session)

    for response, state, code in (
        (
            httpx.Response(429, json={"message": "slow down"}),
            SchwabClientState.RATE_LIMITED,
            "schwab_rate_limited",
        ),
        (
            httpx.Response(503, json={"message": "offline"}),
            SchwabClientState.UNAVAILABLE,
            "schwab_unavailable",
        ),
    ):
        client = _client(repository, httpx.MockTransport(lambda _request, r=response: r))
        with pytest.raises(SchwabClientError, match=code) as error:
            client.get_json(session, "/marketdata/v1/quotes", correlation_id="corr-client")
        assert error.value.state is state

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("provider timed out")

    client = _client(repository, httpx.MockTransport(timeout))
    with pytest.raises(SchwabClientError, match="schwab_timeout") as error:
        client.get_json(session, "/marketdata/v1/quotes", correlation_id="corr-client")
    assert error.value.state is SchwabClientState.UNAVAILABLE


def test_client_quarantines_malformed_json_and_redacts_diagnostics(
    session: Session,
) -> None:
    repository = _store_token(session)
    client = _client(
        repository,
        httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not json")),
    )

    with pytest.raises(SchwabClientError, match="schwab_malformed_json") as error:
        client.get_json(session, "/marketdata/v1/quotes", correlation_id="corr-client")

    assert error.value.state is SchwabClientState.QUARANTINED
    assert "access-token" not in repr(error.value.diagnostics)
    assert error.value.diagnostics["path"] == "/marketdata/v1/quotes"


def _client(
    repository: SchwabTokenRepository,
    transport: httpx.MockTransport,
    *,
    refresh_tokens: Any | None = None,
) -> SchwabReadOnlyClient:
    return SchwabReadOnlyClient(
        token_repository=repository,
        http_client=httpx.Client(transport=transport),
        clock=FrozenClock(NOW),
        refresh_tokens=refresh_tokens,
    )


def _store_token(
    session: Session,
    *,
    access_token: str = "access-token-a",
    refresh_token: str = "refresh-token-a",
    expires_at: datetime = NOW + timedelta(minutes=30),
) -> SchwabTokenRepository:
    repository = SchwabTokenRepository(SchwabTokenCipher("local-key"))
    repository.store_initial(
        session,
        token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
        product="market_data",
        bundle=_bundle(access_token, refresh_token, expires_at=expires_at),
        now=NOW,
        correlation_id="corr-token",
    )
    return repository


def _bundle(
    access_token: str,
    refresh_token: str,
    *,
    expires_at: datetime = NOW + timedelta(minutes=30),
) -> SchwabTokenBundle:
    return SchwabTokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        scope="api",
        access_token_expires_at=expires_at,
        refresh_token_expires_at=NOW + timedelta(days=7),
    )
