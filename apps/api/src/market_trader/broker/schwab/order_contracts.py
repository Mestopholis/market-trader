from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator

from market_trader.paper.models import PaperOrderIntent, PaperOrderType

type SchwabValidationStrategy = Literal["shares", "bull_call", "bear_put"]
type SchwabLegInstruction = Literal["BUY", "SELL", "BUY_TO_OPEN", "SELL_TO_OPEN"]
type SchwabAssetType = Literal["EQUITY", "OPTION"]


class SchwabOrderContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SchwabContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SchwabContractLeg(SchwabContractModel):
    symbol: str
    instruction: SchwabLegInstruction
    asset_type: SchwabAssetType
    quantity: int

    @field_validator("symbol")
    @classmethod
    def _symbol_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized.upper() if " " not in normalized else normalized

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value


class SchwabOrderContractRequest(SchwabContractModel):
    strategy: str
    intent: PaperOrderIntent
    legs: tuple[SchwabContractLeg, ...] = ()


class SchwabValidationContract(SchwabContractModel):
    strategy: SchwabValidationStrategy
    validation_only: bool
    submit_capable: bool
    payload: dict[str, object]


def build_schwab_validation_contract(
    request: SchwabOrderContractRequest,
) -> SchwabValidationContract:
    strategy = _strategy(request.strategy)
    if request.intent.payload.get("submit") is True:
        raise SchwabOrderContractError("live_submission_forbidden")
    _ensure_limit_day_order(request.intent)
    legs = _legs_for_request(strategy=strategy, request=request)
    payload: dict[str, object] = {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": "DAY",
        "price": _money(request.intent.limit_price),
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [_leg_payload(leg) for leg in legs],
    }
    if strategy in {"bull_call", "bear_put"}:
        payload["complexOrderStrategyType"] = "VERTICAL"
    return SchwabValidationContract(
        strategy=strategy,
        validation_only=True,
        submit_capable=False,
        payload=payload,
    )


def _strategy(value: str) -> SchwabValidationStrategy:
    if value in {"shares", "bull_call", "bear_put"}:
        return cast(SchwabValidationStrategy, value)
    raise SchwabOrderContractError("unsupported_strategy")


def _ensure_limit_day_order(intent: PaperOrderIntent) -> None:
    if intent.order_type is not PaperOrderType.LIMIT:
        raise SchwabOrderContractError("unsupported_order_type")
    if intent.time_in_force.lower() != "day":
        raise SchwabOrderContractError("unsupported_time_in_force")


def _legs_for_request(
    *,
    strategy: SchwabValidationStrategy,
    request: SchwabOrderContractRequest,
) -> tuple[SchwabContractLeg, ...]:
    if strategy == "shares":
        if request.legs:
            raise SchwabOrderContractError("shares_must_not_include_option_legs")
        return (
            SchwabContractLeg(
                symbol=request.intent.symbol,
                instruction="BUY" if request.intent.side == "buy" else "SELL",
                asset_type="EQUITY",
                quantity=request.intent.quantity,
            ),
        )
    if len(request.legs) != 2:
        raise SchwabOrderContractError("vertical_spread_requires_two_legs")
    if any(leg.asset_type != "OPTION" for leg in request.legs):
        raise SchwabOrderContractError("vertical_spread_requires_option_legs")
    return request.legs


def _leg_payload(leg: SchwabContractLeg) -> dict[str, object]:
    return {
        "instruction": leg.instruction,
        "quantity": leg.quantity,
        "instrument": {"assetType": leg.asset_type, "symbol": leg.symbol},
    }


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"
