from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.broker.schwab.tokens import (
    SchwabTokenBundle,
    SchwabTokenMetadata,
    SchwabTokenRepository,
)
from market_trader.db.models import SchwabOAuthStateORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import Clock, SystemClock, ensure_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository

SCHWAB_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_MARKET_DATA_TOKEN_ID = "schwab-market-data"
SCHWAB_MARKET_DATA_PRODUCT = "market_data"
_STATE_TTL = timedelta(minutes=10)
_STATE_SCHEMA_VERSION = 1
_AUDIT_SCHEMA_VERSION = 1


class SchwabOAuthError(RuntimeError):
    def __init__(self, code: str, summary: str | None = None) -> None:
        self.code = code
        super().__init__(summary or code)


@dataclass(frozen=True)
class SchwabOAuthConfig:
    client_id: str
    client_secret: str
    callback_url: str
    state_signing_key: str
    authorize_url: str = SCHWAB_AUTHORIZE_URL
    token_url: str = SCHWAB_TOKEN_URL


@dataclass(frozen=True)
class SchwabOAuthStart:
    authorization_url: str
    state: str
    expires_at: datetime


class SchwabOAuthService:
    def __init__(
        self,
        *,
        config: SchwabOAuthConfig,
        token_repository: SchwabTokenRepository,
        http_client: httpx.Client,
        clock: Clock | None = None,
    ) -> None:
        self.config = config
        self.token_repository = token_repository
        self._http_client = http_client
        self._clock = clock or SystemClock()

    def with_clock(self, clock: Clock) -> SchwabOAuthService:
        return SchwabOAuthService(
            config=self.config,
            token_repository=self.token_repository,
            http_client=self._http_client,
            clock=clock,
        )

    def start(self, session: Session, *, correlation_id: str) -> SchwabOAuthStart:
        now = self._now()
        state_id = new_domain_id("schwaboauth")
        nonce = secrets.token_urlsafe(24)
        state = self._sign_state(state_id=state_id, nonce=nonce, issued_at=now)
        expires_at = now + _STATE_TTL
        session.add(
            SchwabOAuthStateORM(
                id=state_id,
                state_hash=self._hash(state),
                nonce_hash=self._hash(nonce),
                callback_url=self.config.callback_url,
                status="pending",
                created_at=now,
                expires_at=expires_at,
                consumed_at=None,
                correlation_id=correlation_id,
            )
        )
        self._audit(
            session,
            correlation_id=correlation_id,
            event_type="schwab.oauth.start",
            subject_id=state_id,
            payload={"expires_at": expires_at.isoformat()},
        )
        query = urlencode(
            {
                "client_id": self.config.client_id,
                "redirect_uri": self.config.callback_url,
                "response_type": "code",
                "state": state,
            }
        )
        return SchwabOAuthStart(
            authorization_url=f"{self.config.authorize_url}?{query}",
            state=state,
            expires_at=expires_at,
        )

    def complete_callback(
        self,
        session: Session,
        *,
        state: str,
        correlation_id: str,
        code: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ) -> SchwabTokenMetadata:
        now = self._now()
        state_row = self._load_state(session, state)
        if state_row.status != "pending":
            raise SchwabOAuthError("oauth_state_replay")
        if _db_utc(state_row.expires_at) <= now:
            state_row.status = "expired"
            self._audit_failure(
                session,
                state_id=state_row.id,
                correlation_id=correlation_id,
                code="oauth_state_expired",
            )
            raise SchwabOAuthError("oauth_state_expired")
        if error is not None:
            state_row.status = "failed"
            state_row.consumed_at = now
            self._audit_failure(
                session,
                state_id=state_row.id,
                correlation_id=correlation_id,
                code="oauth_callback_error",
                payload={"provider_error": error, "summary": error_description},
            )
            raise SchwabOAuthError("oauth_callback_error")
        if not code:
            self._audit_failure(
                session,
                state_id=state_row.id,
                correlation_id=correlation_id,
                code="oauth_code_missing",
            )
            raise SchwabOAuthError("oauth_code_missing")

        bundle = self._exchange_authorization_code(code, now=now)
        self.token_repository.store_initial(
            session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            product=SCHWAB_MARKET_DATA_PRODUCT,
            bundle=bundle,
            now=now,
            correlation_id=correlation_id,
        )
        state_row.status = "consumed"
        state_row.consumed_at = now
        self._audit(
            session,
            correlation_id=correlation_id,
            event_type="schwab.oauth.callback_succeeded",
            subject_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            payload={
                "product": SCHWAB_MARKET_DATA_PRODUCT,
                "scope": bundle.scope,
                "token_type": bundle.token_type,
            },
        )
        return self.token_repository.metadata(
            session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            now=now,
        )

    def refresh(self, session: Session, *, correlation_id: str) -> SchwabTokenMetadata:
        now = self._now()
        existing = self.token_repository.read(session, token_id=SCHWAB_MARKET_DATA_TOKEN_ID)
        bundle = self._exchange_refresh_token(existing.refresh_token, now=now)
        self.token_repository.rotate(
            session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            bundle=bundle,
            now=now,
        )
        self._audit(
            session,
            correlation_id=correlation_id,
            event_type="schwab.oauth.refreshed",
            subject_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            payload={"product": SCHWAB_MARKET_DATA_PRODUCT, "scope": bundle.scope},
        )
        return self.token_repository.metadata(
            session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            now=now,
        )

    def revoke(
        self,
        session: Session,
        *,
        correlation_id: str,
        reason_code: str,
    ) -> SchwabTokenMetadata:
        now = self._now()
        self.token_repository.revoke(
            session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            now=now,
            reason_code=reason_code,
        )
        self._audit(
            session,
            correlation_id=correlation_id,
            event_type="schwab.oauth.revoked",
            subject_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            payload={"reason_code": reason_code},
        )
        return self.token_repository.metadata(
            session,
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            now=now,
        )

    def _exchange_authorization_code(self, code: str, *, now: datetime) -> SchwabTokenBundle:
        response = self._http_client.post(
            self.config.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.callback_url,
            },
            auth=(self.config.client_id, self.config.client_secret),
        )
        response.raise_for_status()
        return self._bundle_from_payload(response.json(), now=now)

    def _exchange_refresh_token(
        self,
        refresh_token: str,
        *,
        now: datetime,
    ) -> SchwabTokenBundle:
        response = self._http_client.post(
            self.config.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(self.config.client_id, self.config.client_secret),
        )
        response.raise_for_status()
        return self._bundle_from_payload(response.json(), now=now)

    def _bundle_from_payload(
        self,
        payload: dict[str, Any],
        *,
        now: datetime,
    ) -> SchwabTokenBundle:
        access_expires = now + timedelta(seconds=int(payload["expires_in"]))
        refresh_expires_in = payload.get("refresh_token_expires_in")
        return SchwabTokenBundle(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            token_type=str(payload.get("token_type", "Bearer")),
            scope=str(payload.get("scope", "")),
            access_token_expires_at=access_expires,
            refresh_token_expires_at=(
                now + timedelta(seconds=int(refresh_expires_in))
                if refresh_expires_in is not None
                else None
            ),
        )

    def _load_state(self, session: Session, state: str) -> SchwabOAuthStateORM:
        decoded = self._verify_state(state)
        row = session.scalar(
            select(SchwabOAuthStateORM).where(SchwabOAuthStateORM.id == decoded.id)
        )
        if row is None or row.state_hash != self._hash(state) or row.nonce_hash != self._hash(
            decoded.nonce
        ):
            raise SchwabOAuthError("oauth_state_invalid")
        return row

    def _sign_state(self, *, state_id: str, nonce: str, issued_at: datetime) -> str:
        payload = {
            "v": _STATE_SCHEMA_VERSION,
            "id": state_id,
            "nonce": nonce,
            "iat": ensure_utc(issued_at).isoformat(),
        }
        encoded = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = self._signature(encoded)
        return f"{encoded}.{signature}"

    def _verify_state(self, state: str) -> _DecodedState:
        try:
            encoded, signature = state.split(".", maxsplit=1)
        except ValueError as error:
            raise SchwabOAuthError("oauth_state_invalid") from error
        expected = self._signature(encoded)
        if not hmac.compare_digest(signature, expected):
            raise SchwabOAuthError("oauth_state_invalid")
        try:
            payload = json.loads(_unb64(encoded))
        except (ValueError, json.JSONDecodeError) as error:
            raise SchwabOAuthError("oauth_state_invalid") from error
        if payload.get("v") != _STATE_SCHEMA_VERSION:
            raise SchwabOAuthError("oauth_state_invalid")
        return _DecodedState(id=str(payload["id"]), nonce=str(payload["nonce"]))

    def _signature(self, encoded_payload: str) -> str:
        return _b64(
            hmac.new(
                self.config.state_signing_key.encode("utf-8"),
                encoded_payload.encode("ascii"),
                hashlib.sha256,
            ).digest()
        )

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _now(self) -> datetime:
        return ensure_utc(self._clock.now())

    def _audit(
        self,
        session: Session,
        *,
        correlation_id: str,
        event_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        AuditRepository(session).append(
            AuditEventCreate(
                correlation_id=correlation_id,
                event_type=event_type,
                actor_type="operator",
                occurred_at=self._now(),
                subject_type="schwab_oauth",
                subject_id=subject_id,
                payload=payload,
                schema_version=_AUDIT_SCHEMA_VERSION,
            )
        )

    def _audit_failure(
        self,
        session: Session,
        *,
        state_id: str,
        correlation_id: str,
        code: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._audit(
            session,
            correlation_id=correlation_id,
            event_type="schwab.oauth.callback_failed",
            subject_id=state_id,
            payload={"code": code, **(payload or {})},
        )


@dataclass(frozen=True)
class _DecodedState:
    id: str
    nonce: str


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("utf-8")


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
