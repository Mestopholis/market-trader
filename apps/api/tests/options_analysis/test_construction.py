from datetime import date
from decimal import Decimal
from pathlib import Path

from market_trader.market_data.models import (
    DeliverableState,
    NormalizedOptionContract,
    PutCall,
)
from market_trader.options_analysis.configuration import (
    OptionsAnalysisPolicy,
    load_options_analysis_policy,
)
from market_trader.options_analysis.construction import (
    construct_bear_put_spreads,
    construct_bull_call_spreads,
)


def test_constructs_a_bull_call_spread_with_exact_payoff_bounds() -> None:
    spreads = construct_bull_call_spreads(
        (_contract("long", Decimal("100"), Decimal("3.00"), Decimal("3.10")),
         _contract("short", Decimal("105"), Decimal("1.00"), Decimal("1.10"))),
        _policy(),
    )

    assert len(spreads) == 1
    spread = spreads[0]
    assert spread.debit == Decimal("2.10")
    assert spread.maximum_loss == Decimal("210.00")
    assert spread.maximum_gain == Decimal("290.00")
    assert spread.break_even == Decimal("102.10")


def test_constructs_a_bear_put_spread_with_exact_payoff_bounds() -> None:
    spreads = construct_bear_put_spreads(
        (_put("long", Decimal("105"), Decimal("3.00"), Decimal("3.10")),
         _put("short", Decimal("100"), Decimal("1.00"), Decimal("1.10"))),
        _policy(),
    )

    assert spreads[0].debit == Decimal("2.10")
    assert spreads[0].maximum_loss == Decimal("210.00")
    assert spreads[0].maximum_gain == Decimal("290.00")
    assert spreads[0].break_even == Decimal("102.90")


def _contract(
    contract_id: str, strike: Decimal, bid: Decimal, ask: Decimal
) -> NormalizedOptionContract:
    return NormalizedOptionContract(
        contract_id=contract_id, expiration=date(2026, 8, 19), strike=strike,
        option_type=PutCall.CALL, deliverable=DeliverableState.STANDARD, bid=bid, ask=ask,
        bid_size=10, ask_size=10, last=None, volume=100, open_interest=1000,
        implied_volatility=Decimal("0.30"), delta=Decimal("0.50"), gamma=Decimal("0.03"),
        theta=Decimal("-0.02"), vega=Decimal("0.10"), quality_reasons=(),
    )


def _put(contract_id: str, strike: Decimal, bid: Decimal, ask: Decimal) -> NormalizedOptionContract:
    return _contract(contract_id, strike, bid, ask).__class__(
        **{**_contract(contract_id, strike, bid, ask).__dict__, "option_type": PutCall.PUT}
    )


def _policy() -> OptionsAnalysisPolicy:
    return load_options_analysis_policy(
        Path(__file__).parents[2]
        / "config"
        / "options_analysis"
        / "options-analysis-policy-v1.json"
    )
