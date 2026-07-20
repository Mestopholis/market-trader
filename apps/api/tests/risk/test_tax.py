from datetime import UTC, datetime, timedelta
from decimal import Decimal

from market_trader.risk.configuration import load_risk_policy
from market_trader.risk.models import (
    BuyingPowerSnapshot,
    ClosedTradeLot,
    RiskCheck,
    RiskCheckState,
    RiskInput,
    ShareProposal,
    TaxLot,
)
from market_trader.risk.tax import evaluate_tax_warnings

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
POLICY = load_risk_policy("config/risk/risk-policy-v1.json")


def test_wash_sale_warning_includes_boundary_and_disclaimer() -> None:
    checks = evaluate_tax_warnings(
        _risk_input(
            closed_trade_lots=(
                _closed_lot("closed:boundary", "AAPL", days_ago=30, taxable=True),
            ),
        ),
        POLICY,
    )

    check = _check(checks, "tax.wash_sale")
    assert check.state is RiskCheckState.WARNING
    assert check.facts["disclaimer"] == POLICY.tax_disclaimer
    assert check.facts["matching_lots"] == ("closed:boundary",)


def test_wash_sale_uses_equivalent_symbol_groups_and_excludes_outside_window() -> None:
    checks = evaluate_tax_warnings(
        _risk_input(
            symbol="SPY",
            closed_trade_lots=(
                _closed_lot("closed:voo", "VOO", days_ago=10, taxable=True),
                _closed_lot("closed:old", "SPY", days_ago=31, taxable=True),
            ),
        ),
        POLICY,
    )

    check = _check(checks, "tax.wash_sale")
    assert check.facts["matching_lots"] == ("closed:voo",)


def test_holding_period_warnings_cover_short_term_and_long_term_boundary() -> None:
    checks = evaluate_tax_warnings(
        _risk_input(
            open_tax_lots=(
                _open_lot("lot:short", "AAPL", days_ago=20, taxable=True),
                _open_lot("lot:long-boundary", "AAPL", days_ago=365, taxable=True),
            ),
        ),
        POLICY,
    )

    assert _check(checks, "tax.short_term_holding_period").facts["matching_lots"] == (
        "lot:short",
    )
    assert _check(checks, "tax.long_term_holding_period").facts["matching_lots"] == (
        "lot:long-boundary",
    )


def test_tax_warnings_ignore_non_taxable_accounts() -> None:
    checks = evaluate_tax_warnings(
        _risk_input(
            open_tax_lots=(_open_lot("lot:ira", "AAPL", days_ago=5, taxable=False),),
            closed_trade_lots=(
                _closed_lot("closed:ira", "AAPL", days_ago=5, taxable=False),
            ),
        ),
        POLICY,
    )

    assert checks == ()


def _risk_input(
    *,
    symbol: str = "AAPL",
    open_tax_lots: tuple[TaxLot, ...] = (),
    closed_trade_lots: tuple[ClosedTradeLot, ...] = (),
) -> RiskInput:
    return RiskInput(
        decision_key="risk:tax",
        proposal=ShareProposal(
            proposal_key=f"proposal:shares:{symbol.lower()}",
            symbol=symbol,
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
        locks=(),
        open_tax_lots=open_tax_lots,
        closed_trade_lots=closed_trade_lots,
        policy_version=POLICY.version,
        policy_hash=POLICY.content_hash,
        as_of=AS_OF,
    )


def _open_lot(lot_key: str, symbol: str, *, days_ago: int, taxable: bool) -> TaxLot:
    return TaxLot(
        lot_key=lot_key,
        symbol=symbol,
        opened_at=AS_OF - timedelta(days=days_ago),
        quantity=1,
        cost_basis=Decimal("100.00"),
        account_taxable=taxable,
    )


def _closed_lot(
    lot_key: str,
    symbol: str,
    *,
    days_ago: int,
    taxable: bool,
) -> ClosedTradeLot:
    return ClosedTradeLot(
        lot_key=lot_key,
        symbol=symbol,
        closed_at=AS_OF - timedelta(days=days_ago),
        quantity=1,
        realized_pl=Decimal("-10.00"),
        loss_amount=Decimal("10.00"),
        account_taxable=taxable,
    )


def _check(checks: tuple[RiskCheck, ...], code: str) -> RiskCheck:
    for check in checks:
        if check.code == code:
            return check
    raise AssertionError(f"missing check {code}")
