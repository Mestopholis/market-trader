from __future__ import annotations

from market_trader.risk.configuration import RiskPolicy
from market_trader.risk.models import (
    RiskCheck,
    RiskCheckSeverity,
    RiskCheckState,
    RiskInput,
    RiskLockSnapshot,
)


def evaluate_locks(risk_input: RiskInput, policy: RiskPolicy) -> tuple[RiskCheck, ...]:
    checks = [
        _lock_check(lock, policy)
        for lock in risk_input.locks
        if lock.status.casefold() == "active"
    ]
    return tuple(sorted(checks, key=lambda check: check.code))


def _lock_check(lock: RiskLockSnapshot, policy: RiskPolicy) -> RiskCheck:
    facts = {
        "lock_id": lock.lock_id,
        "lock_type": lock.lock_type,
        "reason": lock.reason,
        "source_event_id": lock.source_event_id,
    }
    if lock.lock_type in policy.required_lock_types:
        return RiskCheck(
            code=f"lock.{lock.lock_type}",
            severity=RiskCheckSeverity.BLOCK,
            state=RiskCheckState.BLOCKED,
            message=f"active required risk lock: {lock.lock_type}",
            facts=facts,
            source_keys=(lock.lock_id, lock.source_event_id),
        )
    return RiskCheck(
        code=f"lock.{lock.lock_type}",
        severity=RiskCheckSeverity.WARNING,
        state=RiskCheckState.WARNING,
        message=f"active informational risk lock: {lock.lock_type}",
        facts=facts,
        source_keys=(lock.lock_id, lock.source_event_id),
    )
