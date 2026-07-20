from datetime import UTC, datetime
from decimal import Decimal

from market_trader.risk.configuration import load_risk_policy
from market_trader.risk.exposure import evaluate_exposure
from market_trader.risk.models import (
    BuyingPowerSnapshot,
    PortfolioPosition,
    RiskCheck,
    RiskCheckState,
    RiskInput,
    ShareProposal,
    SizingResult,
    WorkingOrderRisk,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
POLICY = load_risk_policy("config/risk/risk-policy-v1.json")


def test_exposure_passes_exactly_at_cash_and_reserved_risk_limits() -> None:
    checks = evaluate_exposure(
        _risk_input(
            settled_cash=Decimal("1250.00"),
            account_equity=Decimal("5000.00"),
        ),
        SizingResult(
            quantity=10,
            notional=Decimal("1000.00"),
            maximum_loss=Decimal("300.00"),
            reserved_risk=Decimal("300.00"),
            assignment_stress=Decimal("0.00"),
            reasons=("test",),
        ),
        POLICY,
    )

    assert _state(checks, "buying_power.settled_cash") is RiskCheckState.PASSED
    assert _state(checks, "exposure.total_reserved_risk") is RiskCheckState.PASSED


def test_exposure_blocks_one_cent_over_settled_cash_or_reserved_risk_limit() -> None:
    checks = evaluate_exposure(
        _risk_input(
            settled_cash=Decimal("1249.99"),
            account_equity=Decimal("5000.00"),
        ),
        SizingResult(
            quantity=10,
            notional=Decimal("1000.00"),
            maximum_loss=Decimal("300.01"),
            reserved_risk=Decimal("300.01"),
            assignment_stress=Decimal("0.00"),
            reasons=("test",),
        ),
        POLICY,
    )

    assert _state(checks, "buying_power.settled_cash") is RiskCheckState.BLOCKED
    assert _state(checks, "exposure.total_reserved_risk") is RiskCheckState.BLOCKED


def test_exposure_blocks_unsettled_cash_dependency_and_flags_borrowed_buying_power() -> None:
    checks = evaluate_exposure(
        _risk_input(
            settled_cash=Decimal("1000.00"),
            unsettled_cash=Decimal("500.00"),
            borrowed_buying_power=Decimal("250.00"),
            account_equity=Decimal("10000.00"),
        ),
        _sizing(notional=Decimal("1100.00"), reserved_risk=Decimal("25.00")),
        POLICY,
    )

    assert _state(checks, "buying_power.unsettled_cash") is RiskCheckState.BLOCKED
    assert _state(checks, "buying_power.borrowed_excluded") is RiskCheckState.WARNING


def test_exposure_counts_working_orders_positions_trades_and_correlation_groups() -> None:
    checks = evaluate_exposure(
        _risk_input(
            settled_cash=Decimal("10000.00"),
            account_equity=Decimal("10000.00"),
            positions=tuple(
                PortfolioPosition(
                    position_key=f"position:{index}",
                    symbol=f"T{index}",
                    quantity=1,
                    market_value=Decimal("100.00"),
                    maximum_loss=Decimal("5.00"),
                    correlation_group="other",
                )
                for index in range(POLICY.max_positions)
            ),
            working_orders=(
                WorkingOrderRisk(
                    order_key="working:1",
                    symbol="AAPL",
                    reserved_risk=Decimal("50.00"),
                    assignment_stress=Decimal("0.00"),
                    correlation_group="mega-cap-tech",
                ),
            ),
            open_trades_today=POLICY.max_open_trades_per_day,
        ),
        _sizing(notional=Decimal("1000.00"), reserved_risk=Decimal("25.00")),
        POLICY,
    )

    assert _state(checks, "exposure.position_count") is RiskCheckState.BLOCKED
    assert _state(checks, "exposure.open_trades_today") is RiskCheckState.BLOCKED
    assert _state(checks, "exposure.total_reserved_risk") is RiskCheckState.PASSED


def test_exposure_blocks_daily_weekly_drawdown_and_correlation_boundaries() -> None:
    checks = evaluate_exposure(
        _risk_input(
            settled_cash=Decimal("10000.00"),
            account_equity=Decimal("10000.00"),
            daily_realized_loss=Decimal("200.01"),
            weekly_realized_loss=Decimal("400.01"),
            peak_equity=Decimal("11000.00"),
            positions=(
                PortfolioPosition(
                    position_key="position:msft",
                    symbol="MSFT",
                    quantity=5,
                    market_value=Decimal("2100.01"),
                    maximum_loss=Decimal("50.00"),
                    correlation_group="mega-cap-tech",
                ),
            ),
        ),
        _sizing(notional=Decimal("900.00"), reserved_risk=Decimal("25.00")),
        POLICY,
    )

    assert _state(checks, "exposure.daily_loss") is RiskCheckState.BLOCKED
    assert _state(checks, "exposure.weekly_loss") is RiskCheckState.BLOCKED
    assert _state(checks, "exposure.drawdown") is RiskCheckState.BLOCKED
    assert _state(checks, "exposure.correlation_group") is RiskCheckState.BLOCKED


def _risk_input(
    *,
    settled_cash: Decimal,
    account_equity: Decimal,
    unsettled_cash: Decimal = Decimal("0.00"),
    borrowed_buying_power: Decimal = Decimal("0.00"),
    positions: tuple[PortfolioPosition, ...] = (),
    working_orders: tuple[WorkingOrderRisk, ...] = (),
    daily_realized_loss: Decimal = Decimal("0.00"),
    weekly_realized_loss: Decimal = Decimal("0.00"),
    peak_equity: Decimal | None = None,
    open_trades_today: int = 0,
) -> RiskInput:
    return RiskInput(
        decision_key="risk:exposure",
        proposal=ShareProposal(
            proposal_key="proposal:shares:aapl",
            symbol="AAPL",
            entry_price=Decimal("100.00"),
            stop_price=Decimal("95.00"),
            direction="long",
        ),
        buying_power=BuyingPowerSnapshot(
            settled_cash=settled_cash,
            unsettled_cash=unsettled_cash,
            reserved_cash=Decimal("0.00"),
            borrowed_buying_power=borrowed_buying_power,
            observed_at=AS_OF,
            snapshot_digest="bp-digest",
        ),
        positions=positions,
        working_orders=working_orders,
        locks=(),
        open_tax_lots=(),
        closed_trade_lots=(),
        policy_version=POLICY.version,
        policy_hash=POLICY.content_hash,
        as_of=AS_OF,
        account_equity=account_equity,
        daily_realized_loss=daily_realized_loss,
        weekly_realized_loss=weekly_realized_loss,
        peak_equity=peak_equity if peak_equity is not None else account_equity,
        open_trades_today=open_trades_today,
    )


def _sizing(*, notional: Decimal, reserved_risk: Decimal) -> SizingResult:
    return SizingResult(
        quantity=1,
        notional=notional,
        maximum_loss=reserved_risk,
        reserved_risk=reserved_risk,
        assignment_stress=Decimal("0.00"),
        reasons=("test",),
    )


def _state(checks: tuple[RiskCheck, ...], code: str) -> RiskCheckState:
    for check in checks:
        if check.code == code:
            return check.state
    raise AssertionError(f"missing check {code}")
