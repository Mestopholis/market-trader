from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from market_trader.config import Settings, get_settings
from market_trader.security.csrf import CSRF_COOKIE_NAME, csrf_token_valid, new_csrf_token
from market_trader.security.passwords import verify_password
from market_trader.security.session import (
    SESSION_COOKIE_NAME,
    SessionAuthError,
    SessionClaims,
    create_session_token,
    validate_session_token,
)

router = APIRouter(prefix="/auth")


class AuthRequiredError(Exception):
    pass


class CsrfFailedError(Exception):
    pass


class LoginRequest(BaseModel):
    username: str
    password: str


def unauthorized_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": "unauthenticated", "summary": "Authentication required."},
        headers={"Cache-Control": "no-store"},
    )


def csrf_failed_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"code": "csrf_failed", "summary": "CSRF token required."},
        headers={"Cache-Control": "no-store"},
    )


async def auth_required_exception_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return unauthorized_response()


async def csrf_failed_exception_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return csrf_failed_response()


@router.post("/login", response_model=None)
def login(payload: LoginRequest, response: Response) -> dict[str, object] | JSONResponse:
    settings = get_settings()
    if not _auth_configured(settings):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"code": "auth_not_configured", "summary": "Authentication is not configured."},
            headers={"Cache-Control": "no-store"},
        )
    if payload.username != settings.auth_username or not verify_password(
        payload.password,
        settings.auth_password_hash or "",
    ):
        return unauthorized_response()

    token = create_session_token(
        username=payload.username,
        issued_at=datetime.now(UTC),
        secret=settings.session_secret or "",
    )
    csrf_token = new_csrf_token()
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=settings.session_ttl_seconds,
        httponly=False,
        secure=True,
        samesite="strict",
    )
    return {"authenticated": True, "username": payload.username}


@router.get("/session", response_model=None)
def session(request: Request) -> dict[str, object] | JSONResponse:
    claims = current_session(request)
    if claims is None:
        return unauthorized_response()
    return {"authenticated": True, "username": claims.username}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(request: Request, response: Response) -> Response | JSONResponse:
    if current_session(request) is None:
        return unauthorized_response()
    if not csrf_token_valid(request):
        return csrf_failed_response()
    response.status_code = status.HTTP_204_NO_CONTENT
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(SESSION_COOKIE_NAME, secure=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE_NAME, secure=True, samesite="strict")
    return response


def current_session(request: Request) -> SessionClaims | None:
    settings = get_settings()
    if not _auth_configured(settings):
        return None
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        return None
    try:
        return validate_session_token(
            token,
            secret=settings.session_secret or "",
            ttl_seconds=settings.session_ttl_seconds,
        )
    except SessionAuthError:
        return None


def _auth_configured(settings: Settings) -> bool:
    return bool(settings.auth_username and settings.auth_password_hash and settings.session_secret)


def require_authenticated_session(request: Request) -> SessionClaims:
    claims = current_session(request)
    if claims is None:
        raise AuthRequiredError
    return claims


def require_csrf_protection(request: Request) -> None:
    require_authenticated_session(request)
    if not csrf_token_valid(request):
        raise CsrfFailedError
