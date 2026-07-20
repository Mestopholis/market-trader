from datetime import date
from decimal import Decimal

from market_trader.options_analysis.warnings import (
    SpreadWarningContext,
    evaluate_spread_warnings,
    warning_severity_for_earnings_state,
    warning_severity_for_pin_distance,
)


def test_active_earnings_risk_blocks_a_spread() -> None:
    assert warning_severity_for_earnings_state("active") == "block"


def test_clear_earnings_state_does_not_block_a_spread() -> None:
    assert warning_severity_for_earnings_state("clear") == "info"


def test_pin_risk_blocks_at_the_policy_boundary() -> None:
    assert warning_severity_for_pin_distance(0.005, 0.005) == "block"


def test_in_the_money_short_call_before_next_ex_dividend_blocks() -> None:
    warnings = evaluate_spread_warnings(
        SpreadWarningContext(
            earnings_state="clear",
            underlying_price=Decimal("105"),
            short_strike=Decimal("100"),
            short_option_type="call",
            expiration=date(2026, 9, 18),
            as_of=date(2026, 8, 14),
            next_session=date(2026, 8, 17),
            ex_dividend_date=date(2026, 8, 17),
            remaining_sessions=20,
            pin_warning_distance=Decimal("0.01"),
            pin_block_distance=Decimal("0.005"),
            minimum_remaining_sessions=2,
        )
    )

    assert [(warning.code, warning.severity) for warning in warnings] == [
        ("early_assignment_risk", "warning"),
        ("ex_dividend_risk", "block"),
    ]


def test_short_put_gets_only_informational_assignment_caveat() -> None:
    warnings = evaluate_spread_warnings(
        SpreadWarningContext(
            earnings_state="clear",
            underlying_price=Decimal("95"),
            short_strike=Decimal("100"),
            short_option_type="put",
            expiration=date(2026, 9, 18),
            as_of=date(2026, 8, 14),
            next_session=date(2026, 8, 17),
            ex_dividend_date=None,
            remaining_sessions=20,
            pin_warning_distance=Decimal("0.01"),
            pin_block_distance=Decimal("0.005"),
            minimum_remaining_sessions=2,
        )
    )

    assert [(warning.code, warning.severity) for warning in warnings] == [
        ("early_assignment_risk", "info"),
    ]


def test_known_ex_dividend_before_expiration_warns_even_when_short_call_is_not_itm() -> None:
    warnings = evaluate_spread_warnings(
        SpreadWarningContext(
            earnings_state="clear",
            underlying_price=Decimal("95"),
            short_strike=Decimal("100"),
            short_option_type="call",
            expiration=date(2026, 9, 18),
            as_of=date(2026, 8, 14),
            next_session=date(2026, 8, 17),
            ex_dividend_date=date(2026, 8, 24),
            remaining_sessions=20,
            pin_warning_distance=Decimal("0.01"),
            pin_block_distance=Decimal("0.005"),
            minimum_remaining_sessions=2,
        )
    )

    assert [(warning.code, warning.severity) for warning in warnings] == [
        ("ex_dividend_risk", "warning"),
    ]
