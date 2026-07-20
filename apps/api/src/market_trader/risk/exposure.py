from __future__ import annotations

from decimal import Decimal

from market_trader.risk.configuration import RiskPolicy
from market_trader.risk.models import (
    PortfolioPosition,
    RiskCheck,
    RiskCheckSeverity,
    RiskCheckState,
    RiskInput,
    SizingResult,
)


def evaluate_exposure(
    risk_input: RiskInput,
    sizing: SizingResult,
    policy: RiskPolicy,
) -> tuple[RiskCheck, ...]:
    checks = [
        _settled_cash_check(risk_input, sizing, policy),
        _unsettled_cash_check(risk_input, sizing, policy),
        _borrowed_buying_power_check(risk_input, policy),
        _total_reserved_risk_check(risk_input, sizing, policy),
        _position_count_check(risk_input, policy),
        _open_trades_today_check(risk_input, policy),
        _daily_loss_check(risk_input, policy),
        _weekly_loss_check(risk_input, policy),
        _drawdown_check(risk_input, policy),
        _correlation_group_check(risk_input, sizing, policy),
    ]
    return tuple(sorted(checks, key=lambda check: check.code))


def _settled_cash_check(
    risk_input: RiskInput,
    sizing: SizingResult,
    policy: RiskPolicy,
) -> RiskCheck:
    required = (
        sizing.notional
        + risk_input.buying_power.reserved_cash
        + policy.min_settled_cash_after_trade
    )
    available = risk_input.buying_power.settled_cash
    passed = available >= required
    return _check(
        code="buying_power.settled_cash",
        passed=passed,
        block_message="settled cash would fall below policy minimum",
        pass_message="settled cash covers trade and policy minimum",
        facts={"available": available, "required": required},
        source_keys=(risk_input.buying_power.snapshot_digest,),
    )


def _unsettled_cash_check(
    risk_input: RiskInput,
    sizing: SizingResult,
    policy: RiskPolicy,
) -> RiskCheck:
    settled_after_minimum = max(
        risk_input.buying_power.settled_cash
        - risk_input.buying_power.reserved_cash
        - policy.min_settled_cash_after_trade,
        Decimal("0.00"),
    )
    depends_on_unsettled = sizing.notional > settled_after_minimum
    blocked = (
        not policy.allow_unsettled_cash
        and risk_input.buying_power.unsettled_cash > 0
        and depends_on_unsettled
    )
    return _check(
        code="buying_power.unsettled_cash",
        passed=not blocked,
        block_message="proposal depends on unsettled cash",
        pass_message="proposal does not depend on unsettled cash",
        facts={
            "allow_unsettled_cash": policy.allow_unsettled_cash,
            "settled_after_minimum": settled_after_minimum,
            "unsettled_cash": risk_input.buying_power.unsettled_cash,
        },
        source_keys=(risk_input.buying_power.snapshot_digest,),
    )


def _borrowed_buying_power_check(risk_input: RiskInput, policy: RiskPolicy) -> RiskCheck:
    borrowed = risk_input.buying_power.borrowed_buying_power
    if policy.block_borrowed_buying_power and borrowed > 0:
        return RiskCheck(
            code="buying_power.borrowed_excluded",
            severity=RiskCheckSeverity.WARNING,
            state=RiskCheckState.WARNING,
            message="borrowed buying power is excluded from risk sizing",
            facts={"borrowed_buying_power": borrowed},
            source_keys=(risk_input.buying_power.snapshot_digest,),
        )
    return RiskCheck(
        code="buying_power.borrowed_excluded",
        severity=RiskCheckSeverity.INFO,
        state=RiskCheckState.PASSED,
        message="no borrowed buying power is included",
        facts={"borrowed_buying_power": borrowed},
        source_keys=(risk_input.buying_power.snapshot_digest,),
    )


def _total_reserved_risk_check(
    risk_input: RiskInput,
    sizing: SizingResult,
    policy: RiskPolicy,
) -> RiskCheck:
    working_reserved = sum(
        (order.reserved_risk for order in risk_input.working_orders),
        Decimal("0.00"),
    )
    total = risk_input.buying_power.reserved_cash + working_reserved + sizing.reserved_risk
    limit = risk_input.account_equity * policy.max_total_reserved_risk_fraction
    return _check(
        code="exposure.total_reserved_risk",
        passed=total <= limit,
        block_message="reserved risk exceeds portfolio limit",
        pass_message="reserved risk is within portfolio limit",
        facts={"limit": limit, "total": total, "working_reserved": working_reserved},
        source_keys=tuple(order.order_key for order in risk_input.working_orders),
    )


def _position_count_check(risk_input: RiskInput, policy: RiskPolicy) -> RiskCheck:
    projected = len(risk_input.positions) + 1
    return _check(
        code="exposure.position_count",
        passed=projected <= policy.max_positions,
        block_message="projected position count exceeds policy limit",
        pass_message="projected position count is within policy limit",
        facts={"limit": policy.max_positions, "projected": projected},
        source_keys=tuple(position.position_key for position in risk_input.positions),
    )


def _open_trades_today_check(risk_input: RiskInput, policy: RiskPolicy) -> RiskCheck:
    projected = risk_input.open_trades_today + 1
    return _check(
        code="exposure.open_trades_today",
        passed=projected <= policy.max_open_trades_per_day,
        block_message="projected daily trade count exceeds policy limit",
        pass_message="projected daily trade count is within policy limit",
        facts={"limit": policy.max_open_trades_per_day, "projected": projected},
        source_keys=(risk_input.decision_key,),
    )


def _daily_loss_check(risk_input: RiskInput, policy: RiskPolicy) -> RiskCheck:
    limit = risk_input.account_equity * policy.max_daily_loss_fraction
    return _check(
        code="exposure.daily_loss",
        passed=risk_input.daily_realized_loss <= limit,
        block_message="daily realized loss exceeds policy limit",
        pass_message="daily realized loss is within policy limit",
        facts={"limit": limit, "realized_loss": risk_input.daily_realized_loss},
        source_keys=(risk_input.decision_key,),
    )


def _weekly_loss_check(risk_input: RiskInput, policy: RiskPolicy) -> RiskCheck:
    limit = risk_input.account_equity * policy.max_weekly_loss_fraction
    return _check(
        code="exposure.weekly_loss",
        passed=risk_input.weekly_realized_loss <= limit,
        block_message="weekly realized loss exceeds policy limit",
        pass_message="weekly realized loss is within policy limit",
        facts={"limit": limit, "realized_loss": risk_input.weekly_realized_loss},
        source_keys=(risk_input.decision_key,),
    )


def _drawdown_check(risk_input: RiskInput, policy: RiskPolicy) -> RiskCheck:
    peak_equity = (
        risk_input.peak_equity
        if risk_input.peak_equity is not None
        else risk_input.account_equity
    )
    drawdown = max(peak_equity - risk_input.account_equity, Decimal("0.00"))
    limit = peak_equity * policy.max_drawdown_fraction
    return _check(
        code="exposure.drawdown",
        passed=drawdown <= limit,
        block_message="portfolio drawdown exceeds policy limit",
        pass_message="portfolio drawdown is within policy limit",
        facts={"drawdown": drawdown, "limit": limit, "peak_equity": peak_equity},
        source_keys=(risk_input.decision_key,),
    )


def _correlation_group_check(
    risk_input: RiskInput,
    sizing: SizingResult,
    policy: RiskPolicy,
) -> RiskCheck:
    group = _proposal_correlation_group(risk_input.proposal.symbol)
    existing = sum(
        (
            position.market_value
            for position in risk_input.positions
            if position.correlation_group == group
        ),
        Decimal("0.00"),
    )
    projected = existing + sizing.notional
    limit = risk_input.account_equity * policy.max_correlation_group_fraction
    source_keys = tuple(
        position.position_key for position in _positions_in_group(risk_input, group)
    )
    return _check(
        code="exposure.correlation_group",
        passed=projected <= limit,
        block_message="correlation group exposure exceeds policy limit",
        pass_message="correlation group exposure is within policy limit",
        facts={"correlation_group": group, "limit": limit, "projected": projected},
        source_keys=source_keys,
    )


def _positions_in_group(risk_input: RiskInput, group: str) -> tuple[PortfolioPosition, ...]:
    return tuple(
        position for position in risk_input.positions if position.correlation_group == group
    )


def _proposal_correlation_group(symbol: str) -> str:
    if symbol.upper() in {"AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AMD", "AVGO"}:
        return "mega-cap-tech"
    return symbol.upper()


def _check(
    *,
    code: str,
    passed: bool,
    block_message: str,
    pass_message: str,
    facts: dict[str, object],
    source_keys: tuple[str, ...],
) -> RiskCheck:
    return RiskCheck(
        code=code,
        severity=RiskCheckSeverity.INFO if passed else RiskCheckSeverity.BLOCK,
        state=RiskCheckState.PASSED if passed else RiskCheckState.BLOCKED,
        message=pass_message if passed else block_message,
        facts=facts,
        source_keys=source_keys,
    )
