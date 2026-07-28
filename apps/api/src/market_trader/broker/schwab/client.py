from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import httpx
from sqlalchemy.orm import Session

from market_trader.broker.schwab.oauth import SCHWAB_MARKET_DATA_TOKEN_ID
from market_trader.broker.schwab.tokens import SchwabTokenRepository
from market_trader.domain.time import Clock, SystemClock, ensure_utc
from market_trader.observability.redaction import redact_value

SCHWAB_MARKET_DATA_BASE_URL = "https://api.schwabapi.com"
_REFRESH_WINDOW = timedelta(minutes=1)

type TokenRefresh = Callable[[Session, str], object]


class SchwabClientState(StrEnum):
    AVAILABLE = "available"
    AUTH_LOCKED = "auth_locked"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class SchwabClientError(RuntimeError):
    code: str
    state: SchwabClientState
    diagnostics: dict[str, object]

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.code)


class SchwabReadOnlyClient:
    def __init__(
        self,
        *,
        token_repository: SchwabTokenRepository,
        http_client: httpx.Client,
        clock: Clock | None = None,
        refresh_tokens: TokenRefresh | None = None,
        base_url: str = SCHWAB_MARKET_DATA_BASE_URL,
    ) -> None:
        self._token_repository = token_repository
        self._http_client = http_client
        self._clock = clock or SystemClock()
        self._refresh_tokens = refresh_tokens
        self._base_url = base_url.rstrip("/")

    def get_json(
        self,
        session: Session,
        path: str,
        *,
        correlation_id: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        self._refresh_if_needed(session, correlation_id=correlation_id)
        bundle = self._token_repository.read(session, token_id=SCHWAB_MARKET_DATA_TOKEN_ID)
        url = f"{self._base_url}{path}"
        try:
            response = self._http_client.get(
                url,
                params=_query_params(params),
                headers={"Authorization": f"Bearer {bundle.access_token}"},
            )
        except httpx.TimeoutException as error:
            raise self._error(
                "schwab_timeout",
                SchwabClientState.UNAVAILABLE,
                path=path,
                correlation_id=correlation_id,
            ) from error
        except httpx.RequestError as error:
            raise self._error(
                "schwab_unavailable",
                SchwabClientState.UNAVAILABLE,
                path=path,
                correlation_id=correlation_id,
            ) from error

        if response.status_code == 401:
            self._token_repository.revoke(
                session,
                token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
                now=self._now(),
                reason_code="provider_unauthorized",
            )
            raise self._error(
                "schwab_auth_locked",
                SchwabClientState.AUTH_LOCKED,
                path=path,
                correlation_id=correlation_id,
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise self._error(
                "schwab_rate_limited",
                SchwabClientState.RATE_LIMITED,
                path=path,
                correlation_id=correlation_id,
                status_code=response.status_code,
            )
        if response.status_code >= 500:
            raise self._error(
                "schwab_unavailable",
                SchwabClientState.UNAVAILABLE,
                path=path,
                correlation_id=correlation_id,
                status_code=response.status_code,
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise self._error(
                "schwab_malformed_json",
                SchwabClientState.QUARANTINED,
                path=path,
                correlation_id=correlation_id,
                status_code=response.status_code,
            ) from error
        if not isinstance(payload, dict):
            raise self._error(
                "schwab_malformed_json",
                SchwabClientState.QUARANTINED,
                path=path,
                correlation_id=correlation_id,
                status_code=response.status_code,
            )
        return payload

    def _refresh_if_needed(self, session: Session, *, correlation_id: str) -> None:
        if self._refresh_tokens is None:
            return
        now = self._now()
        metadata = self._token_repository.metadata(
            session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            now=now,
        )
        if ensure_utc(metadata.access_token_expires_at) - now <= _REFRESH_WINDOW:
            self._refresh_tokens(session, correlation_id)

    def _error(
        self,
        code: str,
        state: SchwabClientState,
        *,
        path: str,
        correlation_id: str,
        status_code: int | None = None,
    ) -> SchwabClientError:
        diagnostics: dict[str, object] = {
            "path": path,
            "correlation_id": correlation_id,
            "status_code": status_code,
        }
        redacted = redact_value(diagnostics)
        return SchwabClientError(
            code=code,
            state=state,
            diagnostics=dict(redacted) if isinstance(redacted, dict) else {},
        )

    def _now(self) -> datetime:
        return ensure_utc(self._clock.now())


def _query_params(
    params: dict[str, object] | None,
) -> dict[str, str | int | float | bool | None] | None:
    if params is None:
        return None
    query: dict[str, str | int | float | bool | None] = {}
    for key, value in params.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            query[key] = value
        else:
            query[key] = str(value)
    return query
