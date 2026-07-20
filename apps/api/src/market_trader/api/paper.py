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

from market_trader.config import get_settings
from market_trader.db.engine import create_engine_from_url
from market_trader.paper.models import ApprovalCard, PaperBrokerScenario
from market_trader.paper.service import PaperLifecycleError, PaperLifecycleService

router = APIRouter(tags=["paper"])


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


@router.post("/approval-cards/{card_key}/approve")
def approve_card(
    card_key: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(service.approve_card(_card(service, card_key)))


@router.post("/approval-cards/{card_key}/modify")
def modify_card(
    card_key: str,
    request: ModifyApprovalRequest,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(
        service.modify_card(
            _card(service, card_key),
            quantity=request.quantity,
            limit_price=request.limit_price,
        )
    )


@router.post("/approval-cards/{card_key}/reject")
def reject_card(
    card_key: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(service.reject_card(_card(service, card_key)))


@router.post("/approvals/{approval_id}/preview")
def preview_approval(
    approval_id: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(service.preview_approval(approval_id))


@router.post("/approvals/{approval_id}/submit")
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
    except PaperLifecycleError as error:
        raise HTTPException(status_code=409, detail=error.code) from error


@router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: str,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(service.cancel_order(order_id))


@router.post("/orders/{order_id}/replace")
def replace_order(
    order_id: str,
    request: ReplaceOrderRequest,
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(service.replace_order(order_id, limit_price=request.limit_price))


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


@router.post("/recover")
def recover(
    response: Response,
    service: Annotated[PaperLifecycleService, Depends(get_paper_lifecycle_service)],
) -> dict[str, Any]:
    _no_store(response)
    return _with_paper_mode(service.recover())


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
