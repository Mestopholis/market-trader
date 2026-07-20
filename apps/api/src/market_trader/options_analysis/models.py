from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from market_trader.domain.time import ensure_utc


class SpreadStrategy(StrEnum):
    BULL_CALL = "bull_call"
    BEAR_PUT = "bear_put"


class EvaluationState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCK = "block"


@dataclass(frozen=True)
class TechnicalReference:
    underlying_price: Decimal
    technical_stop: Decimal
    snapshot_digest: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        if not self.underlying_price.is_finite() or not self.technical_stop.is_finite():
            raise ValueError("technical reference prices must be finite")
        if len(self.snapshot_digest) != 64:
            raise ValueError("technical reference requires a SHA-256 snapshot digest")


@dataclass(frozen=True)
class ContractEvaluation:
    contract_id: str
    state: EvaluationState
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))


@dataclass(frozen=True)
class SpreadCandidate:
    strategy: SpreadStrategy
    long_contract_id: str
    short_contract_id: str
    expiration: date
    debit: Decimal
    maximum_loss: Decimal
    maximum_gain: Decimal
    break_even: Decimal
    net_delta: Decimal
    net_gamma: Decimal
    net_theta: Decimal
    net_vega: Decimal
    liquidity_open_interest: int
    liquidity_volume: int
