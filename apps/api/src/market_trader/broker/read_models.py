from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from market_trader.broker.schwab.oauth import (
    SCHWAB_ACCOUNTS_TRADING_TOKEN_ID,
    SCHWAB_MARKET_DATA_TOKEN_ID,
)
from market_trader.broker.schwab.tokens import SchwabTokenCipher, SchwabTokenRepository
from market_trader.db.models import SchwabMarketDataSyncORM
from market_trader.domain.time import ensure_utc, utc_now

type SchwabConnectionState = Literal[
    "unconfigured",
    "disconnected",
    "connected",
    "expired",
    "revoked",
]
type SchwabAccountsTradingState = Literal[
    "unconfigured",
    "disconnected",
    "connected",
    "expired",
    "revoked",
]
type SchwabMarketDataState = Literal[
    "unconfigured",
    "unknown",
    "available",
    "stale",
    "rate_limited",
    "unavailable",
    "quarantined",
]


class SchwabTokenStatus(BaseModel):
    token_id: str
    product: str
    status: str
    token_type: str
    scope: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime | None
    encryption_key_id: str
    issued_at: datetime
    refreshed_at: datetime | None
    revoked_at: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None
    is_expired: bool


class SchwabMarketDataRefreshStatus(BaseModel):
    sync_key: str
    data_kind: str
    status: str
    provider_state: str
    observed_at: datetime | None
    completed_at: datetime | None
    correlation_id: str
    is_stale: bool


class SchwabBrokerStatus(BaseModel):
    configured: bool
    callback_url: str
    connection_state: SchwabConnectionState
    market_data_state: SchwabMarketDataState
    accounts_trading_configured: bool
    accounts_trading_state: SchwabAccountsTradingState
    token: SchwabTokenStatus | None
    accounts_trading_token: SchwabTokenStatus | None
    last_market_data_refresh: SchwabMarketDataRefreshStatus | None
    actions: dict[str, bool]


class SchwabBrokerStatusReader:
    def __init__(
        self,
        *,
        session: Session,
        token_key: str | None,
        callback_url: str = "https://127.0.0.1:8182",
        configured: bool = True,
        accounts_trading_configured: bool = False,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(minutes=15),
    ) -> None:
        self._session = session
        self._token_key = token_key
        self._callback_url = callback_url
        self._configured = configured
        self._accounts_trading_configured = accounts_trading_configured
        self._now = ensure_utc(now or utc_now())
        self._stale_after = stale_after

    def read(self) -> SchwabBrokerStatus:
        if not self._configured and not self._accounts_trading_configured:
            return SchwabBrokerStatus(
                configured=False,
                callback_url=self._callback_url,
                connection_state="unconfigured",
                market_data_state="unconfigured",
                accounts_trading_configured=False,
                accounts_trading_state="unconfigured",
                token=None,
                accounts_trading_token=None,
                last_market_data_refresh=None,
                actions=_actions(
                    market_data_state="unconfigured",
                    accounts_trading_state="unconfigured",
                    market_data_configured=False,
                    accounts_trading_configured=False,
                ),
            )

        token = self._token_status(SCHWAB_MARKET_DATA_TOKEN_ID) if self._configured else None
        accounts_trading_token = (
            self._token_status(SCHWAB_ACCOUNTS_TRADING_TOKEN_ID)
            if self._accounts_trading_configured
            else None
        )
        refresh = self._last_refresh()
        connection_state = _connection_state(token)
        accounts_trading_state = _connection_state(accounts_trading_token)
        if not self._configured:
            connection_state = "unconfigured"
        if not self._accounts_trading_configured:
            accounts_trading_state = "unconfigured"
        return SchwabBrokerStatus(
            configured=self._configured,
            callback_url=self._callback_url,
            connection_state=connection_state,
            market_data_state=_market_data_state(refresh)
            if self._configured
            else "unconfigured",
            accounts_trading_configured=self._accounts_trading_configured,
            accounts_trading_state=accounts_trading_state,
            token=token,
            accounts_trading_token=accounts_trading_token,
            last_market_data_refresh=refresh,
            actions=_actions(
                market_data_state=connection_state,
                accounts_trading_state=accounts_trading_state,
                market_data_configured=self._configured,
                accounts_trading_configured=self._accounts_trading_configured,
            ),
        )

    def _token_status(self, token_id: str) -> SchwabTokenStatus | None:
        if not self._token_key:
            return None
        try:
            metadata = SchwabTokenRepository(SchwabTokenCipher(self._token_key)).metadata(
                self._session,
                token_id=token_id,
                now=self._now,
            )
        except LookupError:
            return None
        return SchwabTokenStatus.model_validate(metadata, from_attributes=True)

    def _last_refresh(self) -> SchwabMarketDataRefreshStatus | None:
        record = self._session.scalar(
            select(SchwabMarketDataSyncORM)
            .order_by(
                desc(SchwabMarketDataSyncORM.observed_at),
                desc(SchwabMarketDataSyncORM.created_at),
            )
            .limit(1)
        )
        if record is None:
            return None
        observed_at = _stored_utc(record.observed_at) if record.observed_at is not None else None
        return SchwabMarketDataRefreshStatus(
            sync_key=record.sync_key,
            data_kind=record.data_kind,
            status=record.status,
            provider_state=record.provider_state,
            observed_at=observed_at,
            completed_at=(
                _stored_utc(record.completed_at) if record.completed_at is not None else None
            ),
            correlation_id=record.correlation_id,
            is_stale=observed_at is None or self._now - observed_at > self._stale_after,
        )


def _connection_state(token: SchwabTokenStatus | None) -> SchwabConnectionState:
    if token is None:
        return "disconnected"
    if token.status == "revoked":
        return "revoked"
    if token.is_expired:
        return "expired"
    return "connected"


def _market_data_state(
    refresh: SchwabMarketDataRefreshStatus | None,
) -> SchwabMarketDataState:
    if refresh is None:
        return "unknown"
    if refresh.provider_state == "rate_limited":
        return "rate_limited"
    if refresh.provider_state == "unavailable":
        return "unavailable"
    if refresh.provider_state == "quarantined":
        return "quarantined"
    if refresh.is_stale:
        return "stale"
    return "available"


def _actions(
    *,
    market_data_state: SchwabConnectionState,
    accounts_trading_state: SchwabAccountsTradingState,
    market_data_configured: bool,
    accounts_trading_configured: bool,
) -> dict[str, bool]:
    return {
        "oauth_start": market_data_configured,
        "refresh": market_data_state == "connected",
        "revoke": market_data_state == "connected",
        "accounts_oauth_start": accounts_trading_configured,
        "accounts_refresh": accounts_trading_state == "connected",
        "accounts_revoke": accounts_trading_state == "connected",
    }


def _stored_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
