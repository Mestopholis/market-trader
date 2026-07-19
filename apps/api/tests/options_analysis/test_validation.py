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
from market_trader.options_analysis.validation import validate_contracts


def test_accepts_a_standard_contract_at_the_30_dte_boundary() -> None:
    outcome = validate_contracts((_contract(),), _policy(), date(2026, 7, 20))

    assert outcome.accepted == (_contract(),)
    assert outcome.evaluations[0].reasons == ()


def test_rejects_unsupported_deliverables() -> None:
    contract = _contract(deliverable=DeliverableState.UNSUPPORTED)

    outcome = validate_contracts((contract,), _policy(), date(2026, 7, 20))

    assert outcome.accepted == ()
    assert outcome.evaluations[0].reasons == ("contract_nonstandard",)


def test_rejects_a_contract_before_the_30_dte_boundary() -> None:
    contract = _contract(expiration=date(2026, 8, 18))

    outcome = validate_contracts((contract,), _policy(), date(2026, 7, 20))

    assert outcome.evaluations[0].reasons == ("dte_out_of_range",)


def test_rejects_a_crossed_market() -> None:
    contract = _contract(bid=Decimal("2.50"), ask=Decimal("2.40"))

    outcome = validate_contracts((contract,), _policy(), date(2026, 7, 20))

    assert outcome.evaluations[0].reasons == ("contract_crossed_market",)


def test_rejects_a_contract_without_an_executable_bid() -> None:
    outcome = validate_contracts((_contract(bid=Decimal("0")),), _policy(), date(2026, 7, 20))

    assert outcome.evaluations[0].reasons == ("contract_no_bid",)


def test_rejects_a_contract_without_an_executable_ask() -> None:
    outcome = validate_contracts((_contract(ask=Decimal("0")),), _policy(), date(2026, 7, 20))

    assert outcome.evaluations[0].reasons == ("contract_no_ask",)


def test_rejects_contracts_below_the_liquidity_floor() -> None:
    outcome = validate_contracts(
        (_contract(volume=9, open_interest=99),), _policy(), date(2026, 7, 20)
    )

    assert outcome.evaluations[0].reasons == ("liquidity_insufficient",)


def test_rejects_contracts_wider_than_the_policy_limit() -> None:
    outcome = validate_contracts(
        (_contract(bid=Decimal("1.00"), ask=Decimal("1.20")),), _policy(), date(2026, 7, 20)
    )

    assert outcome.evaluations[0].reasons == ("width_excessive",)


def test_rejects_contracts_outside_the_absolute_delta_bands() -> None:
    outcome = validate_contracts((_contract(delta=Decimal("0.10")),), _policy(), date(2026, 7, 20))

    assert outcome.evaluations[0].reasons == ("delta_out_of_range",)


def _contract(**overrides: object) -> NormalizedOptionContract:
    values: dict[str, object] = {
        "contract_id": "AAPL260819C00100000",
        "expiration": date(2026, 8, 19),
        "strike": Decimal("100"),
        "option_type": PutCall.CALL,
        "deliverable": DeliverableState.STANDARD,
        "bid": Decimal("2.40"),
        "ask": Decimal("2.50"),
        "bid_size": 10,
        "ask_size": 10,
        "last": Decimal("2.45"),
        "volume": 100,
        "open_interest": 1000,
        "implied_volatility": Decimal("0.30"),
        "delta": Decimal("0.50"),
        "gamma": Decimal("0.03"),
        "theta": Decimal("-0.02"),
        "vega": Decimal("0.10"),
        "quality_reasons": (),
    }
    values.update(overrides)
    return NormalizedOptionContract(**values)  # type: ignore[arg-type]


def _policy() -> OptionsAnalysisPolicy:
    return load_options_analysis_policy(
        Path(__file__).parents[2]
        / "config"
        / "options_analysis"
        / "options-analysis-policy-v1.json"
    )
