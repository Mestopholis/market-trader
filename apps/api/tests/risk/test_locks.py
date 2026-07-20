from datetime import UTC, datetime
from decimal import Decimal

from market_trader.risk.configuration import load_risk_policy
from market_trader.risk.locks import evaluate_locks
from market_trader.risk.models import (
    BuyingPowerSnapshot,
    RiskCheckState,
    RiskInput,
    RiskLockSnapshot,
    ShareProposal,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
POLICY = load_risk_policy("config/risk/risk-policy-v1.json")


def test_required_active_locks_block_and_are_sorted() -> None:
    checks = evaluate_locks(
        _risk_input(
            (
                _lock("lock:2", "manual", "active"),
                _lock("lock:1", "daily_loss", "active"),
            )
        ),
        POLICY,
    )

    assert [check.code for check in checks] == ["lock.daily_loss", "lock.manual"]
    assert all(check.state is RiskCheckState.BLOCKED for check in checks)
    assert checks[0].facts["lock_id"] == "lock:1"


def test_cleared_required_locks_are_ignored() -> None:
    assert (
        evaluate_locks(
            _risk_input((_lock("lock:1", "daily_loss", "cleared"),)),
            POLICY,
        )
        == ()
    )


def test_informational_active_locks_warn_without_blocking() -> None:
    checks = evaluate_locks(
        _risk_input((_lock("lock:1", "catalyst_warning", "active"),)),
        POLICY,
    )

    assert len(checks) == 1
    assert checks[0].code == "lock.catalyst_warning"
    assert checks[0].state is RiskCheckState.WARNING
    assert checks[0].facts["source_event_id"] == "event:lock:1"


def test_unconfigured_active_locks_are_informational_and_stable() -> None:
    checks = evaluate_locks(
        _risk_input((_lock("lock:1", "broker_disconnect", "active"),)),
        POLICY,
    )

    assert checks[0].state is RiskCheckState.WARNING
    assert tuple(checks[0].facts) == ("lock_id", "lock_type", "reason", "source_event_id")


def _risk_input(locks: tuple[RiskLockSnapshot, ...]) -> RiskInput:
    return RiskInput(
        decision_key="risk:locks",
        proposal=ShareProposal(
            proposal_key="proposal:shares:aapl",
            symbol="AAPL",
            entry_price=Decimal("100.00"),
            stop_price=Decimal("95.00"),
            direction="long",
        ),
        buying_power=BuyingPowerSnapshot(
            settled_cash=Decimal("10000.00"),
            unsettled_cash=Decimal("0.00"),
            reserved_cash=Decimal("0.00"),
            observed_at=AS_OF,
            snapshot_digest="bp-digest",
        ),
        positions=(),
        working_orders=(),
        locks=locks,
        open_tax_lots=(),
        closed_trade_lots=(),
        policy_version=POLICY.version,
        policy_hash=POLICY.content_hash,
        as_of=AS_OF,
    )


def _lock(lock_id: str, lock_type: str, status: str) -> RiskLockSnapshot:
    return RiskLockSnapshot(
        lock_id=lock_id,
        lock_type=lock_type,
        status=status,
        reason=f"{lock_type} reason",
        activated_at=AS_OF,
        source_event_id=f"event:{lock_id}",
    )
