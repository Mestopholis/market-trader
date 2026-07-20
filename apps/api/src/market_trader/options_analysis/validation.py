from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from market_trader.market_data.models import DeliverableState, NormalizedOptionContract
from market_trader.options_analysis.configuration import OptionsAnalysisPolicy
from market_trader.options_analysis.models import ContractEvaluation, EvaluationState


@dataclass(frozen=True)
class ContractValidationOutcome:
    accepted: tuple[NormalizedOptionContract, ...]
    evaluations: tuple[ContractEvaluation, ...]


def validate_contracts(
    contracts: tuple[NormalizedOptionContract, ...], policy: OptionsAnalysisPolicy, as_of: date
) -> ContractValidationOutcome:
    accepted: list[NormalizedOptionContract] = []
    evaluations: list[ContractEvaluation] = []
    for contract in sorted(contracts, key=lambda value: value.contract_id):
        reasons = _reasons(contract, policy, as_of)
        state = EvaluationState.ACCEPTED if not reasons else EvaluationState.REJECTED
        evaluations.append(ContractEvaluation(contract.contract_id, state, reasons))
        if not reasons:
            accepted.append(contract)
    return ContractValidationOutcome(tuple(accepted), tuple(evaluations))


def _reasons(
    contract: NormalizedOptionContract, policy: OptionsAnalysisPolicy, as_of: date
) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        policy.require_standard_deliverable
        and contract.deliverable is not DeliverableState.STANDARD
    ):
        reasons.append("contract_nonstandard")
    dte = (contract.expiration - as_of).days
    if not policy.dte_min <= dte <= policy.dte_max:
        reasons.append("dte_out_of_range")
    if contract.bid <= Decimal(0):
        reasons.append("contract_no_bid")
    if contract.ask <= Decimal(0):
        reasons.append("contract_no_ask")
    if contract.bid > Decimal(0) and contract.ask > Decimal(0) and contract.bid > contract.ask:
        reasons.append("contract_crossed_market")
    if (
        contract.volume is None
        or contract.open_interest is None
        or contract.volume < policy.min_volume
        or contract.open_interest < policy.min_open_interest
    ):
        reasons.append("liquidity_insufficient")
    midpoint = (contract.bid + contract.ask) / Decimal(2)
    if (
        contract.bid > Decimal(0)
        and contract.ask > Decimal(0)
        and midpoint > Decimal(0)
        and (contract.ask - contract.bid) / midpoint > policy.max_leg_relative_width
    ):
        reasons.append("width_excessive")
    if contract.delta is None or not (
        policy.short_delta_min <= abs(contract.delta) <= policy.long_delta_max
    ):
        reasons.append("delta_out_of_range")
    return tuple(reasons)
