from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_trader.risk.configuration import load_risk_policy
from market_trader.risk.models import (
    BuyingPowerSnapshot,
    DebitSpreadProposal,
    RiskInput,
    ShareProposal,
)
from market_trader.risk.sizing import RiskSizingError, size_proposal

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
POLICY = load_risk_policy("config/risk/risk-policy-v1.json")


def test_sizes_share_proposal_by_per_trade_risk_and_rounds_down() -> None:
    result = size_proposal(
        _risk_input(
            ShareProposal(
                proposal_key="proposal:shares:aapl",
                symbol="aapl",
                entry_price=Decimal("100.00"),
                stop_price=Decimal("95.00"),
                direction="long",
            ),
            settled_cash=Decimal("10000.00"),
        ),
        POLICY,
    )

    assert result.quantity == 20
    assert result.notional == Decimal("2000.00")
    assert result.maximum_loss == Decimal("100.00")
    assert result.reserved_risk == Decimal("100.00")
    assert result.assignment_stress == Decimal("0.00")


def test_share_sizing_applies_cash_and_notional_ceilings_before_rounding() -> None:
    result = size_proposal(
        _risk_input(
            ShareProposal(
                proposal_key="proposal:shares:msft",
                symbol="MSFT",
                entry_price=Decimal("333.33"),
                stop_price=Decimal("330.00"),
                direction="long",
            ),
            settled_cash=Decimal("5000.00"),
        ),
        POLICY,
    )

    assert result.quantity == 3
    assert result.notional == Decimal("999.99")
    assert result.maximum_loss == Decimal("9.99")


def test_share_sizing_rejects_zero_quantity() -> None:
    with pytest.raises(RiskSizingError, match="zero quantity"):
        size_proposal(
            _risk_input(
                ShareProposal(
                    proposal_key="proposal:shares:expensive",
                    symbol="TSLA",
                    entry_price=Decimal("1000.00"),
                    stop_price=Decimal("900.00"),
                    direction="long",
                ),
                settled_cash=Decimal("1000.00"),
            ),
            POLICY,
        )


def test_sizes_one_debit_spread_at_contract_boundary() -> None:
    result = size_proposal(
        _risk_input(
            DebitSpreadProposal(
                proposal_key="proposal:spread:spy",
                symbol="SPY",
                long_contract_id="SPY260918C00490000",
                short_contract_id="SPY260918C00500000",
                expiration=AS_OF,
                debit=Decimal("2.50"),
                maximum_loss=Decimal("0.50"),
                short_strike=Decimal("500.00"),
            ),
            settled_cash=Decimal("5000.00"),
        ),
        POLICY,
    )

    assert result.quantity == 1
    assert result.notional == Decimal("250.00")
    assert result.maximum_loss == Decimal("50.00")
    assert result.reserved_risk == Decimal("50.00")
    assert result.assignment_stress == Decimal("50000.00")


def test_spread_sizing_uses_debit_cash_ceiling_and_never_rounds_up() -> None:
    result = size_proposal(
        _risk_input(
            DebitSpreadProposal(
                proposal_key="proposal:spread:qqq",
                symbol="QQQ",
                long_contract_id="QQQ260918C00390000",
                short_contract_id="QQQ260918C00400000",
                expiration=AS_OF,
                debit=Decimal("1.51"),
                maximum_loss=Decimal("0.25"),
                short_strike=Decimal("400.00"),
            ),
            settled_cash=Decimal("10000.00"),
        ),
        POLICY,
    )

    assert result.quantity == 3
    assert result.notional == Decimal("453.00")
    assert result.maximum_loss == Decimal("75.00")
    assert all(isinstance(value, Decimal) for value in (result.notional, result.maximum_loss))


def _risk_input(
    proposal: ShareProposal | DebitSpreadProposal,
    *,
    settled_cash: Decimal,
    reserved_cash: Decimal = Decimal("0.00"),
) -> RiskInput:
    return RiskInput(
        decision_key=f"risk:{proposal.proposal_key}",
        proposal=proposal,
        buying_power=BuyingPowerSnapshot(
            settled_cash=settled_cash,
            unsettled_cash=Decimal("0.00"),
            reserved_cash=reserved_cash,
            observed_at=AS_OF,
            snapshot_digest="bp-digest",
        ),
        positions=(),
        working_orders=(),
        locks=(),
        open_tax_lots=(),
        closed_trade_lots=(),
        policy_version=POLICY.version,
        policy_hash=POLICY.content_hash,
        as_of=AS_OF,
    )
