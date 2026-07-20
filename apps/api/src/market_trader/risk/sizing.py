from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from market_trader.risk.configuration import RiskPolicy
from market_trader.risk.models import (
    DebitSpreadProposal,
    RiskInput,
    ShareProposal,
    SizingResult,
)


class RiskSizingError(ValueError):
    """Raised when a proposal cannot be sized under the active risk policy."""


_CENTS = Decimal("0.01")


def size_proposal(risk_input: RiskInput, policy: RiskPolicy) -> SizingResult:
    proposal = risk_input.proposal
    if isinstance(proposal, ShareProposal):
        return _size_share_proposal(risk_input, proposal, policy)
    if isinstance(proposal, DebitSpreadProposal):
        return _size_spread_proposal(risk_input, proposal, policy)
    raise TypeError(f"unsupported proposal type: {type(proposal)!r}")


def _size_share_proposal(
    risk_input: RiskInput,
    proposal: ShareProposal,
    policy: RiskPolicy,
) -> SizingResult:
    risk_per_share = abs(proposal.entry_price - proposal.stop_price)
    if risk_per_share <= 0:
        raise RiskSizingError("share proposal risk must be positive")

    settled_cash = _available_settled_cash(risk_input, policy)
    risk_budget = risk_input.buying_power.settled_cash * policy.per_trade_risk_fraction
    notional_budget = risk_input.buying_power.settled_cash * policy.max_share_notional_fraction
    quantity = min(
        _whole_units(risk_budget / risk_per_share),
        _whole_units(notional_budget / proposal.entry_price),
        _whole_units(settled_cash / proposal.entry_price),
    )
    if quantity < 1:
        raise RiskSizingError("proposal sizes to zero quantity")

    notional = _money(proposal.entry_price * quantity)
    maximum_loss = _money(risk_per_share * quantity)
    return SizingResult(
        quantity=quantity,
        notional=notional,
        maximum_loss=maximum_loss,
        reserved_risk=maximum_loss,
        assignment_stress=Decimal("0.00"),
        reasons=("cash-ceiling", "notional-ceiling", "per-trade-risk"),
    )


def _size_spread_proposal(
    risk_input: RiskInput,
    proposal: DebitSpreadProposal,
    policy: RiskPolicy,
) -> SizingResult:
    multiplier = policy.contract_multiplier
    debit_per_contract = proposal.debit * multiplier
    loss_per_contract = proposal.maximum_loss * multiplier
    if debit_per_contract <= 0 or loss_per_contract <= 0:
        raise RiskSizingError("spread proposal risk must be positive")

    settled_cash = _available_settled_cash(risk_input, policy)
    risk_budget = risk_input.buying_power.settled_cash * policy.per_trade_risk_fraction
    debit_budget = risk_input.buying_power.settled_cash * policy.max_spread_debit_fraction
    quantity = min(
        _whole_units(risk_budget / loss_per_contract),
        _whole_units(debit_budget / debit_per_contract),
        _whole_units(settled_cash / debit_per_contract),
    )
    if quantity < 1:
        raise RiskSizingError("proposal sizes to zero quantity")

    notional = _money(debit_per_contract * quantity)
    maximum_loss = _money(loss_per_contract * quantity)
    assignment_stress = _money(proposal.short_strike * multiplier * quantity)
    return SizingResult(
        quantity=quantity,
        notional=notional,
        maximum_loss=maximum_loss,
        reserved_risk=maximum_loss,
        assignment_stress=assignment_stress,
        reasons=("cash-ceiling", "debit-ceiling", "per-trade-risk"),
    )


def _available_settled_cash(risk_input: RiskInput, policy: RiskPolicy) -> Decimal:
    settled = (
        risk_input.buying_power.settled_cash
        - risk_input.buying_power.reserved_cash
        - policy.min_settled_cash_after_trade
    )
    return max(settled, Decimal("0.00"))


def _whole_units(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_DOWN)
