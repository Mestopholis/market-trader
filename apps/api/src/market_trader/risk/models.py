from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from market_trader.domain.time import ensure_utc


class RiskDecisionStatus(StrEnum):
    APPROVED = "approved"
    WARNING = "warning"
    BLOCKED = "blocked"


class RiskCheckSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCK = "block"


class RiskCheckState(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    BLOCKED = "blocked"


class ProposalKind(StrEnum):
    SHARES = "shares"
    DEBIT_SPREAD = "debit_spread"


Facts = Mapping[str, object]


@dataclass(frozen=True)
class ShareProposal:
    proposal_key: str
    symbol: str
    entry_price: Decimal
    stop_price: Decimal
    direction: Literal["long", "short"]
    display_note: str = ""

    @property
    def kind(self) -> ProposalKind:
        return ProposalKind.SHARES

    def __post_init__(self) -> None:
        _require_non_empty(self.proposal_key, "proposal_key")
        _require_non_empty(self.symbol, "symbol")
        _require_positive_decimal(self.entry_price, "entry_price")
        _require_positive_decimal(self.stop_price, "stop_price")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class DebitSpreadProposal:
    proposal_key: str
    symbol: str
    long_contract_id: str
    short_contract_id: str
    expiration: datetime
    debit: Decimal
    maximum_loss: Decimal
    short_strike: Decimal
    contracts: int = 1
    display_note: str = ""

    @property
    def kind(self) -> ProposalKind:
        return ProposalKind.DEBIT_SPREAD

    def __post_init__(self) -> None:
        _require_non_empty(self.proposal_key, "proposal_key")
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.long_contract_id, "long_contract_id")
        _require_non_empty(self.short_contract_id, "short_contract_id")
        _require_positive_decimal(self.debit, "debit")
        _require_positive_decimal(self.maximum_loss, "maximum_loss")
        _require_positive_decimal(self.short_strike, "short_strike")
        if self.contracts < 1:
            raise ValueError("contracts must be positive")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "expiration", ensure_utc(self.expiration))


@dataclass(frozen=True)
class BuyingPowerSnapshot:
    settled_cash: Decimal
    unsettled_cash: Decimal
    reserved_cash: Decimal
    observed_at: datetime
    snapshot_digest: str

    def __post_init__(self) -> None:
        _require_non_negative_decimal(self.settled_cash, "settled_cash")
        _require_non_negative_decimal(self.unsettled_cash, "unsettled_cash")
        _require_non_negative_decimal(self.reserved_cash, "reserved_cash")
        _require_non_empty(self.snapshot_digest, "snapshot_digest")
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))


@dataclass(frozen=True)
class PortfolioPosition:
    position_key: str
    symbol: str
    quantity: int
    market_value: Decimal
    maximum_loss: Decimal
    correlation_group: str

    def __post_init__(self) -> None:
        _require_non_empty(self.position_key, "position_key")
        _require_non_empty(self.symbol, "symbol")
        _require_non_negative_decimal(self.market_value, "market_value")
        _require_non_negative_decimal(self.maximum_loss, "maximum_loss")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class WorkingOrderRisk:
    order_key: str
    symbol: str
    reserved_risk: Decimal
    assignment_stress: Decimal
    correlation_group: str

    def __post_init__(self) -> None:
        _require_non_empty(self.order_key, "order_key")
        _require_non_empty(self.symbol, "symbol")
        _require_non_negative_decimal(self.reserved_risk, "reserved_risk")
        _require_non_negative_decimal(self.assignment_stress, "assignment_stress")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class RiskLockSnapshot:
    lock_id: str
    lock_type: str
    status: str
    reason: str
    activated_at: datetime
    source_event_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.lock_id, "lock_id")
        _require_non_empty(self.lock_type, "lock_type")
        _require_non_empty(self.status, "status")
        _require_non_empty(self.source_event_id, "source_event_id")
        object.__setattr__(self, "activated_at", ensure_utc(self.activated_at))


@dataclass(frozen=True)
class TaxLot:
    lot_key: str
    symbol: str
    opened_at: datetime
    quantity: int
    cost_basis: Decimal
    account_taxable: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.lot_key, "lot_key")
        _require_non_empty(self.symbol, "symbol")
        _require_non_negative_decimal(self.cost_basis, "cost_basis")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "opened_at", ensure_utc(self.opened_at))


@dataclass(frozen=True)
class ClosedTradeLot:
    lot_key: str
    symbol: str
    closed_at: datetime
    quantity: int
    realized_pl: Decimal
    loss_amount: Decimal
    account_taxable: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.lot_key, "lot_key")
        _require_non_empty(self.symbol, "symbol")
        _require_finite_decimal(self.realized_pl, "realized_pl")
        _require_non_negative_decimal(self.loss_amount, "loss_amount")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "closed_at", ensure_utc(self.closed_at))


@dataclass(frozen=True)
class RiskInput:
    decision_key: str
    proposal: ShareProposal | DebitSpreadProposal
    buying_power: BuyingPowerSnapshot
    positions: tuple[PortfolioPosition, ...]
    working_orders: tuple[WorkingOrderRisk, ...]
    locks: tuple[RiskLockSnapshot, ...]
    open_tax_lots: tuple[TaxLot, ...]
    closed_trade_lots: tuple[ClosedTradeLot, ...]
    policy_version: str
    policy_hash: str
    as_of: datetime
    display_note: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.decision_key, "decision_key")
        _require_non_empty(self.policy_version, "policy_version")
        _require_non_empty(self.policy_hash, "policy_hash")
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(
            self,
            "positions",
            tuple(sorted(self.positions, key=lambda item: item.position_key)),
        )
        object.__setattr__(
            self,
            "working_orders",
            tuple(sorted(self.working_orders, key=lambda item: item.order_key)),
        )
        object.__setattr__(self, "locks", tuple(sorted(self.locks, key=lambda item: item.lock_id)))
        object.__setattr__(
            self,
            "open_tax_lots",
            tuple(sorted(self.open_tax_lots, key=lambda item: item.lot_key)),
        )
        object.__setattr__(
            self,
            "closed_trade_lots",
            tuple(sorted(self.closed_trade_lots, key=lambda item: item.lot_key)),
        )


@dataclass(frozen=True)
class SizingResult:
    quantity: int
    notional: Decimal
    maximum_loss: Decimal
    reserved_risk: Decimal
    assignment_stress: Decimal
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity must be non-negative")
        _require_non_negative_decimal(self.notional, "notional")
        _require_non_negative_decimal(self.maximum_loss, "maximum_loss")
        _require_non_negative_decimal(self.reserved_risk, "reserved_risk")
        _require_non_negative_decimal(self.assignment_stress, "assignment_stress")
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))


@dataclass(frozen=True)
class RiskCheck:
    code: str
    severity: RiskCheckSeverity
    state: RiskCheckState
    message: str
    facts: Facts
    source_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")
        object.__setattr__(self, "facts", _freeze_facts(self.facts))
        object.__setattr__(self, "source_keys", tuple(sorted(set(self.source_keys))))


@dataclass(frozen=True)
class RiskDecision:
    decision_key: str
    status: RiskDecisionStatus
    proposal_kind: ProposalKind
    sizing: SizingResult
    checks: tuple[RiskCheck, ...]
    policy_version: str
    policy_hash: str
    input_digest: str
    result_digest: str
    as_of: datetime
    explanation: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.decision_key, "decision_key")
        _require_non_empty(self.policy_version, "policy_version")
        _require_non_empty(self.policy_hash, "policy_hash")
        _require_non_empty(self.input_digest, "input_digest")
        _require_non_empty(self.result_digest, "result_digest")
        object.__setattr__(self, "as_of", ensure_utc(self.as_of))
        object.__setattr__(self, "checks", tuple(sorted(self.checks, key=lambda item: item.code)))


def _freeze_facts(value: Facts) -> Facts:
    return MappingProxyType(
        {
            str(key): _freeze_fact_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        },
    )


def _freeze_fact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_facts(value)
    if isinstance(value, tuple | list):
        return tuple(_freeze_fact_value(item) for item in value)
    if isinstance(value, Decimal):
        _require_finite_decimal(value, "fact")
    return value


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_positive_decimal(value: Decimal, name: str) -> None:
    _require_finite_decimal(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_non_negative_decimal(value: Decimal, name: str) -> None:
    _require_finite_decimal(value, name)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_finite_decimal(value: Decimal, name: str) -> None:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
