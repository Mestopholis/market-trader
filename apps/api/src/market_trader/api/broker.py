from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from functools import lru_cache
from html import escape
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from market_trader.api.auth import require_authenticated_session, require_csrf_protection
from market_trader.broker.read_models import SchwabBrokerStatus, SchwabBrokerStatusReader
from market_trader.broker.schwab.client import SchwabReadOnlyClient
from market_trader.broker.schwab.live_data import (
    SchwabLiveMarketDataIngestionResult,
    SchwabLiveMarketDataIngestionService,
)
from market_trader.broker.schwab.market_data import SchwabMarketDataProvider
from market_trader.broker.schwab.oauth import (
    SCHWAB_ACCOUNTS_TRADING_PRODUCT,
    SCHWAB_ACCOUNTS_TRADING_TOKEN_ID,
    SCHWAB_MARKET_DATA_PRODUCT,
    SCHWAB_MARKET_DATA_TOKEN_ID,
    SchwabOAuthConfig,
    SchwabOAuthError,
    SchwabOAuthService,
)
from market_trader.broker.schwab.tokens import SchwabTokenCipher, SchwabTokenRepository
from market_trader.config import get_settings
from market_trader.db.engine import create_engine_from_url
from market_trader.observability.correlation import CorrelationContext
from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.live_scan import SchwabLiveScannerService, SchwabLiveScanResult

MUTATING_DEPENDENCIES = [
    Depends(require_authenticated_session),
    Depends(require_csrf_protection),
]

router = APIRouter(prefix="/broker", tags=["broker"])


class SchwabQuoteRefreshRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)


class SchwabQuoteRefreshResponse(BaseModel):
    sync_key: str
    data_kind: str
    symbols: tuple[str, ...]
    provider_state: str
    accepted: int
    degraded: int
    stale: int
    quarantined: int
    deduplicated: int


class SchwabLiveScanRequest(BaseModel):
    source: str = Field(default="schwab", min_length=1)
    as_of: datetime | None = None
    observed_lookback_minutes: int = Field(default=15, ge=1, le=390)


class SchwabLiveScanResponse(BaseModel):
    source: str
    run_key: str
    result_digest: str
    counts: dict[str, int]


def get_schwab_oauth_service() -> SchwabOAuthService:
    settings = get_settings()
    return SchwabOAuthService(
        config=SchwabOAuthConfig(
            client_id=settings.schwab_client_id or "",
            client_secret=settings.schwab_client_secret or "",
            callback_url=settings.schwab_callback_url,
            state_signing_key=settings.schwab_token_encryption_key or "",
            token_id=SCHWAB_MARKET_DATA_TOKEN_ID,
            product=SCHWAB_MARKET_DATA_PRODUCT,
        ),
        token_repository=SchwabTokenRepository(
            SchwabTokenCipher(settings.schwab_token_encryption_key or "")
        ),
        http_client=_http_client(),
    )


def get_schwab_live_market_data_service(
    session: Annotated[Session, Depends(get_schwab_session)],
) -> SchwabLiveMarketDataIngestionService:
    settings = get_settings()
    token_repository = SchwabTokenRepository(
        SchwabTokenCipher(settings.schwab_token_encryption_key or "")
    )
    oauth_service = get_schwab_oauth_service()
    return SchwabLiveMarketDataIngestionService(
        provider=SchwabMarketDataProvider(
            client=SchwabReadOnlyClient(
                token_repository=token_repository,
                http_client=_http_client(),
                refresh_tokens=lambda db_session, correlation_id: oauth_service.refresh(
                    db_session,
                    correlation_id=correlation_id,
                ),
            ),
            session=session,
        )
    )


def get_schwab_live_scanner_service() -> SchwabLiveScannerService:
    return SchwabLiveScannerService(
        configuration=load_scanner_configuration("config/scanner")
    )


def get_schwab_accounts_trading_oauth_service() -> SchwabOAuthService:
    settings = get_settings()
    return SchwabOAuthService(
        config=SchwabOAuthConfig(
            client_id=settings.schwab_accounts_trading_client_id or "",
            client_secret=settings.schwab_accounts_trading_client_secret or "",
            callback_url=settings.schwab_callback_url,
            state_signing_key=settings.schwab_token_encryption_key or "",
            token_id=SCHWAB_ACCOUNTS_TRADING_TOKEN_ID,
            product=SCHWAB_ACCOUNTS_TRADING_PRODUCT,
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
        accounts_trading_configured=settings.schwab_accounts_trading_enabled,
    ).read()


@router.post(
    "/schwab/market-data/quotes/refresh",
    response_model=SchwabQuoteRefreshResponse,
    dependencies=MUTATING_DEPENDENCIES,
)
def refresh_schwab_market_data_quotes(
    request: Request,
    response: Response,
    payload: SchwabQuoteRefreshRequest,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[
        SchwabLiveMarketDataIngestionService,
        Depends(get_schwab_live_market_data_service),
    ],
) -> SchwabLiveMarketDataIngestionResult:
    _no_store(response)
    try:
        return service.refresh_quotes(
            session,
            symbols=tuple(symbol.strip().upper() for symbol in payload.symbols),
            correlation_id=_correlation_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/schwab/market-data/scan-live",
    response_model=SchwabLiveScanResponse,
    dependencies=MUTATING_DEPENDENCIES,
)
def scan_live_schwab_market_data(
    request: Request,
    response: Response,
    payload: SchwabLiveScanRequest,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[
        SchwabLiveScannerService,
        Depends(get_schwab_live_scanner_service),
    ],
) -> SchwabLiveScanResult:
    _no_store(response)
    try:
        return service.scan(
            session,
            source=payload.source.strip().lower(),
            as_of=payload.as_of,
            observed_lookback_minutes=payload.observed_lookback_minutes,
            correlation_id=_correlation_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/schwab/oauth/callback", response_model=None)
def complete_schwab_oauth_callback(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[SchwabOAuthService, Depends(get_schwab_oauth_service)],
    state: Annotated[str, Query(min_length=1)],
    code: Annotated[str | None, Query(min_length=1)] = None,
    error: Annotated[str | None, Query(min_length=1)] = None,
    error_description: Annotated[str | None, Query(min_length=1)] = None,
) -> Response | dict[str, Any]:
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
    payload = {"status": "connected", "token": _json(metadata)}
    if _wants_html(request):
        return _schwab_callback_success_page(payload, title="Schwab Market Data connected")
    return payload


@router.get("/schwab/accounts/oauth/callback", response_model=None)
def complete_schwab_accounts_trading_oauth_callback(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[
        SchwabOAuthService,
        Depends(get_schwab_accounts_trading_oauth_service),
    ],
    state: Annotated[str, Query(min_length=1)],
    code: Annotated[str | None, Query(min_length=1)] = None,
    error: Annotated[str | None, Query(min_length=1)] = None,
    error_description: Annotated[str | None, Query(min_length=1)] = None,
) -> Response | dict[str, Any]:
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
    payload = {"status": "connected", "token": _json(metadata)}
    if _wants_html(request):
        return _schwab_callback_success_page(
            payload,
            title="Schwab Accounts and Trading connected",
        )
    return payload


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


@router.post("/schwab/accounts/oauth/start", dependencies=MUTATING_DEPENDENCIES)
def start_schwab_accounts_trading_oauth(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[
        SchwabOAuthService,
        Depends(get_schwab_accounts_trading_oauth_service),
    ],
) -> dict[str, Any]:
    _no_store(response)
    return _json(service.start(session, correlation_id=_correlation_id(request)))


@router.post("/schwab/accounts/oauth/refresh", dependencies=MUTATING_DEPENDENCIES)
def refresh_schwab_accounts_trading_oauth(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[
        SchwabOAuthService,
        Depends(get_schwab_accounts_trading_oauth_service),
    ],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _json(service.refresh(session, correlation_id=_correlation_id(request)))
    except SchwabOAuthError as exc:
        raise _oauth_http_error(exc) from exc


@router.post("/schwab/accounts/oauth/revoke", dependencies=MUTATING_DEPENDENCIES)
def revoke_schwab_accounts_trading_oauth(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_schwab_session)],
    service: Annotated[
        SchwabOAuthService,
        Depends(get_schwab_accounts_trading_oauth_service),
    ],
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


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept.lower()


def _schwab_callback_success_page(payload: dict[str, Any], *, title: str) -> HTMLResponse:
    token = payload.get("token", {})
    token_payload = token if isinstance(token, dict) else {}
    expires_at = escape(str(token_payload.get("access_token_expires_at", "unknown")))
    product = escape(str(token_payload.get("product", "schwab")))
    status = escape(str(token_payload.get("status", "connected")))
    safe_title = escape(title)
    return HTMLResponse(
        content=f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, -apple-system, sans-serif; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #101418;
      color: #f5f7fa;
    }}
    main {{
      width: min(560px, calc(100vw - 32px));
      border: 1px solid #2c3642;
      border-radius: 8px;
      padding: 24px;
      background: #171d24;
    }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    dl {{
      display: grid;
      grid-template-columns: max-content minmax(0, 1fr);
      gap: 8px 14px;
      margin: 18px 0;
    }}
    dt {{ color: #aab4bc; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    a {{ color: #8fb7ff; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }}
    .button {{
      display: inline-block;
      padding: 10px 14px;
      border-radius: 6px;
      background: #4f8cff;
      color: white;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <dl>
      <dt>Product</dt><dd>{product}</dd>
      <dt>Status</dt><dd>{status}</dd>
      <dt>Access expires</dt><dd>{expires_at}</dd>
    </dl>
    <div class="actions">
      <a class="button" href="http://127.0.0.1:5173/">Open dashboard</a>
      <a href="https://127.0.0.1:8182/">Back to Schwab Connect</a>
    </div>
  </main>
</body>
</html>
        """,
        headers={"Cache-Control": "no-store"},
    )


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
