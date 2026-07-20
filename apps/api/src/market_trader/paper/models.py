from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from market_trader.domain.time import ensure_utc

MAX_DISPLAY_TEXT = 200
MAX_PAYLOAD_TEXT = 500
MAX_PAYLOAD_DEPTH = 4
FORBIDDEN_PAYLOAD_KEY_PARTS = (
    "account",
    "api_key",
    "broker",
    "credential",
    "live_mode",
    "password",
    "schwab",
    "secret",
    "token",
)


class ApprovalCardState(StrEnum):
    READY = "ready"
    STALE = "stale"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


class PaperOrderStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    WORKING = "working"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELED = "canceled"
    REPLACED = "replaced"
    TIMED_OUT = "timed_out"
    RECONCILED = "reconciled"


class PaperPositionStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    EXPIRED = "expired"
    ASSIGNED = "assigned"


class PaperOrderType(StrEnum):
    LIMIT = "limit"


class PaperAction(StrEnum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"
    PREVIEW = "preview"
    SUBMIT = "submit_paper_order"
    CANCEL = "cancel_paper_order"
    REPLACE = "replace_paper_order"


class PaperBrokerScenario(StrEnum):
    ACCEPTED_UNFILLED = "accepted_unfilled"
    FULL_FILL = "full_fill"
    PARTIAL_FILL = "partial_fill"
    REJECT = "reject"
    CANCEL = "cancel"
    CANCEL_REPLACE = "cancel_replace"
    TIMEOUT = "timeout"
    ASSIGNMENT = "assignment"


class PaperModel(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=True)


class ApprovalCard(PaperModel):
    card_key: str
    state: ApprovalCardState
    candidate_key: str
    symbol: str
    direction: str
    proposal_kind: str
    quantity: int
    limit_price: Decimal
    maximum_loss: Decimal
    risk_decision_key: str
    risk_status: str
    risk_input_digest: str
    risk_result_digest: str
    source_keys: tuple[str, ...]
    allowed_actions: tuple[PaperAction, ...]
    expires_at: datetime
    as_of: datetime
    warnings: tuple[str, ...] = ()
    paper_mode: bool = True

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return _non_empty(value, "symbol").upper()

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: int) -> int:
        return _positive_int(value, "quantity")

    @field_validator("limit_price")
    @classmethod
    def _limit_price_valid(cls, value: Decimal) -> Decimal:
        return _positive_decimal(value, "price")

    @field_validator("maximum_loss")
    @classmethod
    def _maximum_loss_valid(cls, value: Decimal) -> Decimal:
        return _non_negative_decimal(value, "maximum loss")

    @field_validator("risk_input_digest", "risk_result_digest")
    @classmethod
    def _digest_valid(cls, value: str) -> str:
        return _digest(value)

    @field_validator("source_keys")
    @classmethod
    def _source_keys_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_non_empty(value, "source key")

    @field_validator("allowed_actions")
    @classmethod
    def _actions_sorted(cls, value: tuple[PaperAction, ...]) -> tuple[PaperAction, ...]:
        return tuple(sorted(set(value), key=lambda action: action.value))

    @field_validator("expires_at", "as_of")
    @classmethod
    def _datetime_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("warnings")
    @classmethod
    def _warnings_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item[:MAX_DISPLAY_TEXT] for item in value)


class PaperOrderIntent(PaperModel):
    intent_key: str
    approval_id: str
    proposed_trade_id: str
    risk_decision_key: str
    symbol: str
    side: str
    order_type: PaperOrderType
    quantity: int
    limit_price: Decimal
    time_in_force: str
    source_keys: tuple[str, ...]
    correlation_id: str
    created_at: datetime
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("order_type", mode="before")
    @classmethod
    def _limit_only(cls, value: object) -> object:
        if value != PaperOrderType.LIMIT and value != PaperOrderType.LIMIT.value:
            raise ValueError("limit orders only")
        return value

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return _non_empty(value, "symbol").upper()

    @field_validator("side")
    @classmethod
    def _side_valid(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        return normalized

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: int) -> int:
        return _positive_int(value, "quantity")

    @field_validator("limit_price")
    @classmethod
    def _limit_price_valid(cls, value: Decimal) -> Decimal:
        return _positive_decimal(value, "price")

    @field_validator("source_keys")
    @classmethod
    def _source_keys_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_non_empty(value, "source key")

    @field_validator("created_at")
    @classmethod
    def _datetime_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _payload_safe(self) -> Self:
        _validate_payload(self.payload)
        return self


class PaperPreview(PaperModel):
    preview_key: str
    approval_id: str
    intent_key: str
    quote_observed_at: datetime
    quote_expires_at: datetime
    bid: Decimal
    ask: Decimal
    limit_price: Decimal
    estimated_maximum_loss: Decimal
    reserved_risk: Decimal
    warnings: tuple[str, ...]
    preview_digest: str
    source_keys: tuple[str, ...]
    as_of: datetime

    @field_validator("quote_observed_at", "quote_expires_at", "as_of")
    @classmethod
    def _datetime_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("bid", "ask", "limit_price")
    @classmethod
    def _prices_valid(cls, value: Decimal) -> Decimal:
        return _positive_decimal(value, "price")

    @field_validator("estimated_maximum_loss", "reserved_risk")
    @classmethod
    def _loss_valid(cls, value: Decimal) -> Decimal:
        return _non_negative_decimal(value, "maximum loss")

    @field_validator("warnings")
    @classmethod
    def _warnings_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item[:MAX_DISPLAY_TEXT] for item in value)

    @field_validator("preview_digest")
    @classmethod
    def _digest_valid(cls, value: str) -> str:
        return _digest(value)

    @field_validator("source_keys")
    @classmethod
    def _source_keys_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_non_empty(value, "source key")


class PaperBrokerOrder(PaperModel):
    order_id: str
    intent_key: str
    status: PaperOrderStatus
    scenario: PaperBrokerScenario
    requested_quantity: int
    filled_quantity: int
    remaining_quantity: int
    limit_price: Decimal
    average_fill_price: Decimal | None
    simulated_broker_reference: str
    correlation_id: str
    source_keys: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None
    broker_reference: None = None

    @field_validator("requested_quantity")
    @classmethod
    def _requested_positive(cls, value: int) -> int:
        return _positive_int(value, "quantity")

    @field_validator("filled_quantity", "remaining_quantity")
    @classmethod
    def _quantities_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("quantity must be non-negative")
        return value

    @field_validator("limit_price")
    @classmethod
    def _limit_price_valid(cls, value: Decimal) -> Decimal:
        return _positive_decimal(value, "price")

    @field_validator("average_fill_price")
    @classmethod
    def _average_fill_price_valid(cls, value: Decimal | None) -> Decimal | None:
        return _positive_decimal(value, "price") if value is not None else None

    @field_validator("source_keys")
    @classmethod
    def _source_keys_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_non_empty(value, "source key")

    @field_validator("created_at", "updated_at", "terminal_at")
    @classmethod
    def _datetime_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def _quantities_balance(self) -> Self:
        if self.filled_quantity + self.remaining_quantity != self.requested_quantity:
            raise ValueError("filled and remaining quantities must equal requested quantity")
        return self


class PaperPosition(PaperModel):
    position_key: str
    symbol: str
    status: PaperPositionStatus
    quantity: int
    average_price: Decimal
    realized_pl: Decimal
    unrealized_pl: Decimal
    source_order_ids: tuple[str, ...]
    source_fill_ids: tuple[str, ...]
    risk_decision_key: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    exit_rules: dict[str, object] = Field(default_factory=dict)
    broker_reference: None = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return _non_empty(value, "symbol").upper()

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: int) -> int:
        return _positive_int(value, "quantity")

    @field_validator("average_price")
    @classmethod
    def _average_price_valid(cls, value: Decimal) -> Decimal:
        return _positive_decimal(value, "price")

    @field_validator("realized_pl", "unrealized_pl")
    @classmethod
    def _pl_finite(cls, value: Decimal) -> Decimal:
        return _finite_decimal(value, "p/l")

    @field_validator("source_order_ids", "source_fill_ids")
    @classmethod
    def _sources_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_non_empty(value, "source key")

    @field_validator("opened_at", "updated_at", "closed_at")
    @classmethod
    def _datetime_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def _exit_rules_safe(self) -> Self:
        _validate_payload(self.exit_rules)
        return self


class LifecycleEvent(PaperModel):
    event_key: str
    event_type: str
    subject_type: str
    subject_id: str
    occurred_at: datetime
    correlation_id: str
    source_keys: tuple[str, ...]
    payload: dict[str, object]

    @field_validator("occurred_at")
    @classmethod
    def _datetime_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("source_keys")
    @classmethod
    def _source_keys_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_non_empty(value, "source key")

    @model_validator(mode="after")
    def _payload_safe(self) -> Self:
        _validate_payload(self.payload)
        return self


def _non_empty(value: str, name: str) -> str:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value


def _positive_int(value: int, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _finite_decimal(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def _positive_decimal(value: Decimal, name: str) -> Decimal:
    _finite_decimal(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _non_negative_decimal(value: Decimal, name: str) -> Decimal:
    _finite_decimal(value, name)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _digest(value: str) -> str:
    value = _non_empty(value, "digest")
    if len(value) > 128:
        raise ValueError("digest is too long")
    return value


def _sorted_non_empty(value: tuple[str, ...], name: str) -> tuple[str, ...]:
    return tuple(sorted({_non_empty(item, name) for item in value}))


def _validate_payload(value: object, *, depth: int = 0) -> None:
    if depth > MAX_PAYLOAD_DEPTH:
        raise ValueError("payload nesting is too deep")
    if isinstance(value, str):
        if len(value) > MAX_PAYLOAD_TEXT:
            raise ValueError("payload text is too long")
        return
    if isinstance(value, Decimal):
        _finite_decimal(value, "payload decimal")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized != "simulated_broker_reference" and any(
                part in normalized for part in FORBIDDEN_PAYLOAD_KEY_PARTS
            ):
                raise ValueError("paper lifecycle payload contains forbidden key")
            _validate_payload(item, depth=depth + 1)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _validate_payload(item, depth=depth + 1)
