from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from market_trader.api.auth import require_authenticated_session, require_csrf_protection
from market_trader.config import get_settings
from market_trader.db.engine import create_engine_from_url
from market_trader.paper.models import ApprovalCard, PaperBrokerScenario
from market_trader.paper.service import PaperLifecycleError, PaperLifecycleService
from market_trader.system_state.blocking import SystemBlockedError

MUTATING_DEPENDENCIES = [Depends(require_csrf_protection)]

router = APIRouter(tags=["paper"], dependencies=[Depends(require_authenticated_session)])


class ModifyApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1)
    limit_price: Decimal = Field(gt=0)


class SubmitApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_digest: str = Field(min_length=1, max_length=128)
    scenario: PaperBrokerScenario = PaperBrokerScenario.FULL_FILL


class ReplaceOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit_price: Decimal = Field(gt=0)


def get_paper_lifecycle_service() -> Generator[PaperLifecycleService]:
    session = Session(_engine())
    try:
        yield PaperLifecycleService(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/approval-cards")
def approval_cards(
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return {"paper_mode": True, "approval_cards": _json(service.approval_cards())}


@router.post("/approval-cards/{card_key}/approve", dependencies=MUTATING_DEPENDENCIES)
def approve_card(
    card_key: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _with_paper_mode(service.approve_card(_card(service, card_key)))
    except (SystemBlockedError, PaperLifecycleError) as error:
        if isinstance(error, PaperLifecycleError) and not _is_blocking_code(error.code):
            raise
        raise HTTPException(
            status_code=423,
            detail=_blocked_response(error),
            headers={"Cache-Control": "no-store"},
        ) from error


@router.post("/approval-cards/{card_key}/modify", dependencies=MUTATING_DEPENDENCIES)
def modify_card(
    card_key: str,
    request: ModifyApprovalRequest,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _with_paper_mode(
            service.modify_card(
                _card(service, card_key),
                quantity=request.quantity,
                limit_price=request.limit_price,
            )
        )
    except (SystemBlockedError, PaperLifecycleError) as error:
        if isinstance(error, PaperLifecycleError) and not _is_blocking_code(error.code):
            raise
        raise HTTPException(
            status_code=423,
            detail=_blocked_response(error),
            headers={"Cache-Control": "no-store"},
        ) from error


@router.post("/approval-cards/{card_key}/reject", dependencies=MUTATING_DEPENDENCIES)
def reject_card(
    card_key: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _with_paper_mode(service.reject_card(_card(service, card_key)))
    except (SystemBlockedError, PaperLifecycleError) as error:
        if isinstance(error, PaperLifecycleError) and not _is_blocking_code(error.code):
            raise
        raise HTTPException(
            status_code=423,
            detail=_blocked_response(error),
            headers={"Cache-Control": "no-store"},
        ) from error


@router.post("/approvals/{approval_id}/preview", dependencies=MUTATING_DEPENDENCIES)
def preview_approval(
    approval_id: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _with_paper_mode(service.preview_approval(approval_id))
    except (SystemBlockedError, PaperLifecycleError) as error:
        if isinstance(error, PaperLifecycleError) and not _is_blocking_code(error.code):
            raise
        raise HTTPException(
            status_code=423,
            detail=_blocked_response(error),
            headers={"Cache-Control": "no-store"},
        ) from error


@router.post("/approvals/{approval_id}/submit", dependencies=MUTATING_DEPENDENCIES)
def submit_approval(
    approval_id: str,
    request: SubmitApprovalRequest,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _with_paper_mode(
            service.submit_approval(
                approval_id,
                preview_digest=request.preview_digest,
                scenario=request.scenario,
            )
        )
    except (SystemBlockedError, PaperLifecycleError) as error:
        if isinstance(error, PaperLifecycleError) and not _is_blocking_code(error.code):
            raise HTTPException(status_code=409, detail=error.code) from error
        raise HTTPException(
            status_code=423,
            detail=_blocked_response(error),
            headers={"Cache-Control": "no-store"},
        ) from error


@router.post("/orders/{order_id}/cancel", dependencies=MUTATING_DEPENDENCIES)
def cancel_order(
    order_id: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _with_paper_mode(service.cancel_order(order_id))
    except (SystemBlockedError, PaperLifecycleError) as error:
        if isinstance(error, PaperLifecycleError) and not _is_blocking_code(error.code):
            raise
        raise HTTPException(
            status_code=423,
            detail=_blocked_response(error),
            headers={"Cache-Control": "no-store"},
        ) from error


@router.post("/orders/{order_id}/replace", dependencies=MUTATING_DEPENDENCIES)
def replace_order(
    order_id: str,
    request: ReplaceOrderRequest,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    try:
        return _with_paper_mode(service.replace_order(order_id, limit_price=request.limit_price))
    except (SystemBlockedError, PaperLifecycleError) as error:
        if isinstance(error, PaperLifecycleError) and not _is_blocking_code(error.code):
            raise
        raise HTTPException(
            status_code=423,
            detail=_blocked_response(error),
            headers={"Cache-Control": "no-store"},
        ) from error


@router.get("/orders")
def orders(
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    recovery = service.recover()
    return {"paper_mode": True, "orders": _json(_field(recovery, "open_orders"))}


@router.get("/positions")
def positions(
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    recovery = service.recover()
    return {"paper_mode": True, "positions": _json(_field(recovery, "open_positions"))}


@router.post("/recover", dependencies=MUTATING_DEPENDENCIES)
def recover(
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(service.recover())


def _blocked_response(error: SystemBlockedError | PaperLifecycleError) -> dict[str, Any]:
    code = error.code
    component = (
        error.component if isinstance(error, SystemBlockedError) else _component_from_code(code)
    )
    return {
        "paper_mode": True,
        "code": code,
        "component": component,
        "summary": "Paper action is blocked by system readiness state.",
    }


def _is_blocking_code(code: str) -> bool:
    return _component_from_code(code) != "system_state"


def _component_from_code(code: str) -> str:
    if code.startswith("backup"):
        return "backup"
    if code.startswith("provider"):
        return "provider"
    if code.startswith("required_risk"):
        return "risk_locks"
    if code.startswith("paper_reconciliation"):
        return "paper_reconciliation"
    if code.startswith("restart_recovery"):
        return "restart_recovery"
    if code.startswith("stale_market"):
        return "market_data_freshness"
    return "system_state"


def _card(service: PaperLifecycleService, card_key: str) -> ApprovalCard:
    for card in service.approval_cards():
        if card.card_key == card_key:
            return card
    raise HTTPException(status_code=404, detail="approval_card_not_found")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _with_paper_mode(value: object) -> dict[str, Any]:
    payload = _json(value)
    if not isinstance(payload, dict):
        return {"paper_mode": True, "data": payload}
    payload["paper_mode"] = True
    return payload


def _json(value: object) -> Any:
    if hasattr(value, "model_dump"):
        return jsonable_encoder(value)
    if hasattr(value, "__dict__"):
        return jsonable_encoder(vars(value))
    return jsonable_encoder(value)


def _field(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


@lru_cache
def _engine() -> Engine:
    return create_engine_from_url(get_settings().database_url)
