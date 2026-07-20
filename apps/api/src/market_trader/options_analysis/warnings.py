from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SpreadWarning:
    code: str
    severity: str


@dataclass(frozen=True)
class SpreadWarningContext:
    earnings_state: str
    underlying_price: Decimal
    short_strike: Decimal
    short_option_type: str
    expiration: date
    as_of: date
    next_session: date
    ex_dividend_date: date | None
    remaining_sessions: int
    pin_warning_distance: Decimal
    pin_block_distance: Decimal
    minimum_remaining_sessions: int


def evaluate_spread_warnings(context: SpreadWarningContext) -> tuple[SpreadWarning, ...]:
    warnings: list[SpreadWarning] = []
    earnings_severity = warning_severity_for_earnings_state(context.earnings_state)
    if earnings_severity == "block":
        warnings.append(SpreadWarning("earnings_risk", earnings_severity))
    in_the_money = (
        context.underlying_price > context.short_strike
        if context.short_option_type == "call"
        else context.underlying_price < context.short_strike
    )
    if context.short_option_type == "put":
        warnings.append(SpreadWarning("early_assignment_risk", "info"))
    elif context.ex_dividend_date is not None and context.ex_dividend_date < context.expiration:
        if in_the_money:
            warnings.append(SpreadWarning("early_assignment_risk", "warning"))
        is_imminent = in_the_money and context.ex_dividend_date <= context.next_session
        severity = "block" if is_imminent else "warning"
        warnings.append(SpreadWarning("ex_dividend_risk", severity))
    if context.remaining_sessions <= context.minimum_remaining_sessions:
        warnings.append(SpreadWarning("expiration_risk", "warning"))
    distance = abs(context.underlying_price - context.short_strike) / context.short_strike
    if distance <= context.pin_warning_distance:
        warnings.append(
            SpreadWarning(
                "pin_risk",
                warning_severity_for_pin_distance(distance, context.pin_block_distance),
            )
        )
    return tuple(sorted(warnings, key=lambda warning: warning.code))


def warning_severity_for_earnings_state(state: str) -> str:
    if state in {"active", "stale", "unresolved", "missing"}:
        return "block"
    return "info"


def warning_severity_for_pin_distance(
    distance: Decimal | float, block_distance: Decimal | float
) -> str:
    if distance <= block_distance:
        return "block"
    return "warning"
