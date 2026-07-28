from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from market_trader.api.auth import require_authenticated_session, require_csrf_protection
from market_trader.broker.read_models import SchwabBrokerStatus, SchwabBrokerStatusReader
from market_trader.broker.schwab.oauth import (
    SchwabOAuthConfig,
    SchwabOAuthError,
    SchwabOAuthService,
)
from market_trader.broker.schwab.tokens import SchwabTokenCipher, SchwabTokenRepository
from market_trader.config import get_settings
from market_trader.db.engine import create_engine_from_url
from market_trader.observability.correlation import CorrelationContext

MUTATING_DEPENDENCIES = [
    Depends(require_authenticated_session),
    Depends(require_csrf_protection),
]

router = APIRouter(prefix="/broker", tags=["broker"])


def get_schwab_oauth_service() -> SchwabOAuthService:
    settings = get_settings()
    return SchwabOAuthService(
        config=SchwabOAuthConfig(
            client_id=settings.schwab_client_id or "",
            client_secret=settings.schwab_client_secret or "",
            callback_url=settings.schwab_callback_url,
            state_signing_key=settings.schwab_token_encryption_key or "",
        ),
        token_repository=SchwabTokenRepository(
            SchwabTokenCipher(settings.schwab_token_encryption_key or "")
        ),
        http_client=_http_client(),
    )


def get_schwab_session() -> Generator[Session]:
    session = Session(_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.post("/schwab/oauth/start", dependencies=MUTATING_DEPENDENCIES)
def start_schwab_oauth(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[SchwabOAuthService, Depends(get_schwab_oauth_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _json(service.start(session, correlation_id=_correlation_id(request)))


@router.get(
    "/schwab/status",
    response_model=SchwabBrokerStatus,
    dependencies=[Depends(require_authenticated_session)],
)
def schwab_status(
    session: Annotated[Session, Depends(get_schwab_session)],
) -> SchwabBrokerStatus:
    settings = get_settings()
    return SchwabBrokerStatusReader(
        session=session,
        token_key=settings.schwab_token_encryption_key,
        callback_url=settings.schwab_callback_url,
        configured=settings.schwab_market_data_enabled,
    ).read()


@router.get("/schwab/oauth/callback")
def complete_schwab_oauth_callback(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[SchwabOAuthService, Depends(get_schwab_oauth_service)],
    state: Annotated[str, Query(min_length=1)],
    code: Annotated[str | None, Query(min_length=1)] = None,
    error: Annotated[str | None, Query(min_length=1)] = None,
    error_description: Annotated[str | None, Query(min_length=1)] = None,
) -> dict[str, Any]:
    _no_store(response)
    try:
        metadata = service.complete_callback(
            session,
            state=state,
            code=code,
            error=error,
            error_description=error_description,
            correlation_id=_correlation_id(request),
        )
    except SchwabOAuthError as exc:
        raise _oauth_http_error(exc) from exc
    return {"status": "connected", "token": _json(metadata)}


@router.post("/schwab/oauth/refresh", dependencies=MUTATING_DEPENDENCIES)
def refresh_schwab_oauth(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[SchwabOAuthService, Depends(get_schwab_oauth_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _json(service.refresh(session, correlation_id=_correlation_id(request)))
    except SchwabOAuthError as exc:
        raise _oauth_http_error(exc) from exc


@router.post("/schwab/oauth/revoke", dependencies=MUTATING_DEPENDENCIES)
def revoke_schwab_oauth(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[SchwabOAuthService, Depends(get_schwab_oauth_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _json(
        service.revoke(
            session,
            correlation_id=_correlation_id(request),
            reason_code="operator_revoked",
        )
    )


def _oauth_http_error(error: SchwabOAuthError) -> HTTPException:
    status_code = 409 if error.code in {"oauth_state_replay"} else 400
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "summary": str(error)},
        headers={"Cache-Control": "no-store"},
    )


def _correlation_id(request: Request) -> str:
    context = getattr(request.state, "correlation_context", None)
    if isinstance(context, CorrelationContext):
        return context.correlation_id
    return "corr-unavailable"


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _json(value: object) -> dict[str, Any]:
    payload = jsonable_encoder(value)
    if not isinstance(payload, dict):
        return {"data": payload}
    return payload


@lru_cache
def _engine() -> Engine:
    return create_engine_from_url(get_settings().database_url)


@lru_cache
def _http_client() -> httpx.Client:
    return httpx.Client(timeout=10.0)
