from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime

from market_trader.domain.time import ensure_utc, utc_now

SESSION_COOKIE_NAME = "market_trader_session"


class SessionAuthError(ValueError):
    pass


@dataclass(frozen=True)
class SessionClaims:
    username: str
    issued_at: datetime


def create_session_token(*, username: str, issued_at: datetime, secret: str) -> str:
    payload = {"username": username, "issued_at": ensure_utc(issued_at).isoformat()}
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _signature(encoded_payload, secret)
    return f"{encoded_payload}.{signature}"


def validate_session_token(token: str, *, secret: str, ttl_seconds: int) -> SessionClaims:
    try:
        encoded_payload, supplied_signature = token.split(".", 1)
    except ValueError as error:
        raise SessionAuthError("invalid session") from error
    expected_signature = _signature(encoded_payload, secret)
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise SessionAuthError("invalid session")
    try:
        payload = json.loads(_b64decode(encoded_payload))
        username = payload["username"]
        issued_at = datetime.fromisoformat(payload["issued_at"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SessionAuthError("invalid session") from error
    if not isinstance(username, str) or not username:
        raise SessionAuthError("invalid session")
    claims = SessionClaims(username=username, issued_at=ensure_utc(issued_at))
    age_seconds = (utc_now() - claims.issued_at).total_seconds()
    if age_seconds < 0 or age_seconds > ttl_seconds:
        raise SessionAuthError("expired session")
    return claims


def _signature(encoded_payload: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
