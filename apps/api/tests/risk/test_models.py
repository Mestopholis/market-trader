from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_trader.risk.models import (
    BuyingPowerSnapshot,
    ClosedTradeLot,
    PortfolioPosition,
    ProposalKind,
    RiskCheck,
    RiskCheckSeverity,
    RiskCheckState,
    RiskDecision,
    RiskDecisionStatus,
    RiskInput,
    RiskLockSnapshot,
    ShareProposal,
    SizingResult,
    TaxLot,
    WorkingOrderRisk,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def test_risk_records_are_immutable_and_mapping_facts_are_read_only() -> None:
    check = RiskCheck(
        code="cash.available",
        severity=RiskCheckSeverity.INFO,
        state=RiskCheckState.PASSED,
        message="cash is available",
        facts={"available_cash": Decimal("1000.00")},
        source_keys=("bp:snapshot",),
    )

    with pytest.raises(FrozenInstanceError):
        check.code = "changed"  # type: ignore[misc]

    with pytest.raises(TypeError):
        check.facts["available_cash"] = Decimal("0.00")  # type: ignore[index]


def test_utc_timestamps_are_enforced_and_normalized() -> None:
    local_like = datetime(2026, 7, 20, 10, 30, tzinfo=timezone(timedelta(hours=-5)))
    snapshot = BuyingPowerSnapshot(
        settled_cash=Decimal("1000.00"),
        unsettled_cash=Decimal("25.00"),
        reserved_cash=Decimal("100.00"),
        observed_at=local_like,
        snapshot_digest="bp-digest",
    )

    assert snapshot.observed_at == AS_OF

    with pytest.raises(ValueError, match="timezone-aware"):
        BuyingPowerSnapshot(
            settled_cash=Decimal("1000.00"),
            unsettled_cash=Decimal("25.00"),
            reserved_cash=Decimal("100.00"),
            observed_at=datetime(2026, 7, 20, 15, 30),
            snapshot_digest="bp-digest",
        )


def test_nonfinite_or_negative_decimal_amounts_are_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        ShareProposal(
            proposal_key="proposal:bad",
            symbol="AAPL",
            entry_price=Decimal("NaN"),
            stop_price=Decimal("190.00"),
            direction="long",
        )

    with pytest.raises(ValueError, match="non-negative"):
        SizingResult(
            quantity=1,
            notional=Decimal("10.00"),
            maximum_loss=Decimal("-0.01"),
            reserved_risk=Decimal("10.00"),
            assignment_stress=Decimal("0.00"),
            reasons=("bad-loss",),
        )


def test_risk_input_sorts_collections_for_deterministic_identity() -> None:
    check_b = RiskCheck(
        code="z.lock",
        severity=RiskCheckSeverity.BLOCK,
        state=RiskCheckState.BLOCKED,
        message="blocked",
        facts={"lock": "daily_loss"},
        source_keys=("lock:2", "lock:1"),
    )
    check_a = RiskCheck(
        code="a.cash",
        severity=RiskCheckSeverity.INFO,
        state=RiskCheckState.PASSED,
        message="passed",
        facts={"cash": Decimal("1000.00")},
        source_keys=("bp:1",),
    )
    decision = RiskDecision(
        decision_key="risk:1",
        status=RiskDecisionStatus.BLOCKED,
        proposal_kind=ProposalKind.SHARES,
        sizing=SizingResult(
            quantity=2,
            notional=Decimal("400.00"),
            maximum_loss=Decimal("20.00"),
            reserved_risk=Decimal("20.00"),
            assignment_stress=Decimal("0.00"),
            reasons=("risk-budget",),
        ),
        checks=(check_b, check_a),
        policy_version="risk-policy-v1",
        policy_hash="abc123",
        input_digest="input",
        result_digest="result",
        as_of=AS_OF,
        explanation="display text",
    )

    assert [check.code for check in decision.checks] == ["a.cash", "z.lock"]
    assert decision.checks[1].source_keys == ("lock:1", "lock:2")


def test_risk_input_contract_carries_offline_context_without_order_payloads() -> None:
    risk_input = RiskInput(
        decision_key="risk:input:1",
        proposal=ShareProposal(
            proposal_key="proposal:shares:aapl",
            symbol="AAPL",
            entry_price=Decimal("200.00"),
            stop_price=Decimal("190.00"),
            direction="long",
        ),
        buying_power=BuyingPowerSnapshot(
            settled_cash=Decimal("5000.00"),
            unsettled_cash=Decimal("0.00"),
            reserved_cash=Decimal("0.00"),
            observed_at=AS_OF,
            snapshot_digest="bp-digest",
        ),
        positions=(
            PortfolioPosition(
                position_key="position:msft",
                symbol="MSFT",
                quantity=10,
                market_value=Decimal("4000.00"),
                maximum_loss=Decimal("250.00"),
                correlation_group="mega-cap-tech",
            ),
        ),
        working_orders=(
            WorkingOrderRisk(
                order_key="working:1",
                symbol="AAPL",
                reserved_risk=Decimal("75.00"),
                assignment_stress=Decimal("0.00"),
                correlation_group="mega-cap-tech",
            ),
        ),
        locks=(
            RiskLockSnapshot(
                lock_id="lock:1",
                lock_type="daily_loss",
                status="active",
                reason="daily limit hit",
                activated_at=AS_OF - timedelta(hours=1),
                source_event_id="event:1",
            ),
        ),
        open_tax_lots=(
            TaxLot(
                lot_key="lot:1",
                symbol="AAPL",
                opened_at=AS_OF - timedelta(days=20),
                quantity=5,
                cost_basis=Decimal("210.00"),
                account_taxable=True,
            ),
        ),
        closed_trade_lots=(
            ClosedTradeLot(
                lot_key="closed:1",
                symbol="AAPL",
                closed_at=AS_OF - timedelta(days=10),
                quantity=5,
                realized_pl=Decimal("-50.00"),
                loss_amount=Decimal("50.00"),
                account_taxable=True,
            ),
        ),
        policy_version="risk-policy-v1",
        policy_hash="abc123",
        as_of=AS_OF,
        display_note="display only",
    )

    assert risk_input.proposal.kind is ProposalKind.SHARES
    assert risk_input.positions[0].position_key == "position:msft"
    assert not hasattr(risk_input, "order_payload")
