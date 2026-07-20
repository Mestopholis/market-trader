from datetime import UTC, datetime, timedelta
from decimal import Decimal

from market_trader.risk.configuration import load_risk_policy
from market_trader.risk.engine import RiskEngine
from market_trader.risk.models import (
    BuyingPowerSnapshot,
    ClosedTradeLot,
    RiskDecisionStatus,
    RiskInput,
    RiskLockSnapshot,
    ShareProposal,
)
from market_trader.risk.serialization import canonical_record

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
POLICY = load_risk_policy("config/risk/risk-policy-v1.json")


def test_engine_approves_clean_risk_input_with_stable_digests() -> None:
    decision = RiskEngine().evaluate(_risk_input(), POLICY)

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.input_digest
    assert decision.result_digest
    assert decision.reason_summary == ("approved",)


def test_engine_returns_warning_when_only_warning_checks_exist() -> None:
    decision = RiskEngine().evaluate(
        _risk_input(
            closed_trade_lots=(
                ClosedTradeLot(
                    lot_key="closed:1",
                    symbol="AAPL",
                    closed_at=AS_OF - timedelta(days=5),
                    quantity=1,
                    realized_pl=Decimal("-10.00"),
                    loss_amount=Decimal("10.00"),
                    account_taxable=True,
                ),
            )
        ),
        POLICY,
    )

    assert decision.status is RiskDecisionStatus.WARNING
    assert "tax.wash_sale" in decision.reason_summary


def test_engine_blocks_when_any_blocking_check_exists() -> None:
    decision = RiskEngine().evaluate(
        _risk_input(
            locks=(
                RiskLockSnapshot(
                    lock_id="lock:1",
                    lock_type="daily_loss",
                    status="active",
                    reason="daily loss hit",
                    activated_at=AS_OF,
                    source_event_id="event:1",
                ),
            )
        ),
        POLICY,
    )

    assert decision.status is RiskDecisionStatus.BLOCKED
    assert "lock.daily_loss" in decision.reason_summary


def test_engine_orders_checks_and_result_digest_deterministically() -> None:
    first = RiskEngine().evaluate(
        _risk_input(
            locks=(
                RiskLockSnapshot(
                    lock_id="lock:2",
                    lock_type="manual",
                    status="active",
                    reason="manual stop",
                    activated_at=AS_OF,
                    source_event_id="event:2",
                ),
                RiskLockSnapshot(
                    lock_id="lock:1",
                    lock_type="daily_loss",
                    status="active",
                    reason="daily loss hit",
                    activated_at=AS_OF,
                    source_event_id="event:1",
                ),
            )
        ),
        POLICY,
    )
    second = RiskEngine().evaluate(
        _risk_input(
            locks=(
                RiskLockSnapshot(
                    lock_id="lock:1",
                    lock_type="daily_loss",
                    status="active",
                    reason="daily loss hit",
                    activated_at=AS_OF,
                    source_event_id="event:1",
                ),
                RiskLockSnapshot(
                    lock_id="lock:2",
                    lock_type="manual",
                    status="active",
                    reason="manual stop",
                    activated_at=AS_OF,
                    source_event_id="event:2",
                ),
            )
        ),
        POLICY,
    )

    assert [check.code for check in first.checks] == sorted(check.code for check in first.checks)
    assert first.result_digest == second.result_digest


def test_engine_decision_contains_no_order_or_approval_payloads() -> None:
    record = canonical_record(RiskEngine().evaluate(_risk_input(), POLICY))
    encoded = str(record).casefold()

    assert "order_payload" not in encoded
    assert "approval" not in encoded
    assert "broker" not in encoded


def _risk_input(
    *,
    locks: tuple[RiskLockSnapshot, ...] = (),
    closed_trade_lots: tuple[ClosedTradeLot, ...] = (),
) -> RiskInput:
    return RiskInput(
        decision_key="risk:engine",
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
        closed_trade_lots=closed_trade_lots,
        policy_version=POLICY.version,
        policy_hash=POLICY.content_hash,
        as_of=AS_OF,
        account_equity=Decimal("10000.00"),
    )
