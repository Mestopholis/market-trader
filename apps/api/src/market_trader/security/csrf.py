from __future__ import annotations

import hmac
import secrets

from fastapi import Request

CSRF_COOKIE_NAME = "market_trader_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_token_valid(request: Request) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)
