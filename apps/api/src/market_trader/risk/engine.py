from __future__ import annotations

from decimal import Decimal

from market_trader.risk.configuration import RiskPolicy
from market_trader.risk.exposure import evaluate_exposure
from market_trader.risk.locks import evaluate_locks
from market_trader.risk.models import (
    RiskCheck,
    RiskCheckSeverity,
    RiskCheckState,
    RiskDecision,
    RiskDecisionStatus,
    RiskInput,
    SizingResult,
)
from market_trader.risk.serialization import stable_digest
from market_trader.risk.sizing import RiskSizingError, size_proposal
from market_trader.risk.tax import evaluate_tax_warnings


class RiskEngine:
    def evaluate(self, risk_input: RiskInput, policy: RiskPolicy) -> RiskDecision:
        sizing, sizing_checks = _size_or_block(risk_input, policy)
        checks = tuple(
            sorted(
                (
                    *sizing_checks,
                    *evaluate_exposure(risk_input, sizing, policy),
                    *evaluate_locks(risk_input, policy),
                    *evaluate_tax_warnings(risk_input, policy),
                ),
                key=lambda check: check.code,
            )
        )
        status = _decision_status(checks)
        reason_summary = _reason_summary(status, checks)
        input_digest = stable_digest(risk_input)
        result_digest = stable_digest(
            {
                "checks": checks,
                "input_digest": input_digest,
                "policy_hash": policy.content_hash,
                "policy_version": policy.version,
                "proposal_kind": risk_input.proposal.kind,
                "reason_summary": reason_summary,
                "sizing": sizing,
                "status": status,
            }
        )
        return RiskDecision(
            decision_key=risk_input.decision_key,
            status=status,
            proposal_kind=risk_input.proposal.kind,
            sizing=sizing,
            checks=checks,
            policy_version=policy.version,
            policy_hash=policy.content_hash,
            input_digest=input_digest,
            result_digest=result_digest,
            as_of=risk_input.as_of,
            explanation="; ".join(reason_summary),
            reason_summary=reason_summary,
        )


def _size_or_block(
    risk_input: RiskInput,
    policy: RiskPolicy,
) -> tuple[SizingResult, tuple[RiskCheck, ...]]:
    try:
        return size_proposal(risk_input, policy), ()
    except RiskSizingError as error:
        return (
            SizingResult(
                quantity=0,
                notional=Decimal("0.00"),
                maximum_loss=Decimal("0.00"),
                reserved_risk=Decimal("0.00"),
                assignment_stress=Decimal("0.00"),
                reasons=("sizing-error",),
            ),
            (
                RiskCheck(
                    code="sizing.zero_quantity",
                    severity=RiskCheckSeverity.BLOCK,
                    state=RiskCheckState.BLOCKED,
                    message=str(error),
                    facts={"error": str(error)},
                    source_keys=(risk_input.decision_key,),
                ),
            ),
        )


def _decision_status(checks: tuple[RiskCheck, ...]) -> RiskDecisionStatus:
    if any(check.state is RiskCheckState.BLOCKED for check in checks):
        return RiskDecisionStatus.BLOCKED
    if any(check.state is RiskCheckState.WARNING for check in checks):
        return RiskDecisionStatus.WARNING
    return RiskDecisionStatus.APPROVED


def _reason_summary(
    status: RiskDecisionStatus,
    checks: tuple[RiskCheck, ...],
) -> tuple[str, ...]:
    if status is RiskDecisionStatus.APPROVED:
        return ("approved",)
    return tuple(
        check.code
        for check in checks
        if check.state
        is (
            RiskCheckState.BLOCKED
            if status is RiskDecisionStatus.BLOCKED
            else RiskCheckState.WARNING
        )
    )
