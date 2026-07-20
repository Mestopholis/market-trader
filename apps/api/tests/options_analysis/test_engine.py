from datetime import date
from decimal import Decimal

from market_trader.options_analysis.engine import OptionsAnalysisEngine
from market_trader.options_analysis.models import SpreadCandidate, SpreadStrategy


def _spread(long_contract_id: str, short_contract_id: str, debit: str) -> SpreadCandidate:
    return SpreadCandidate(
        strategy=SpreadStrategy.BULL_CALL,
        long_contract_id=long_contract_id,
        short_contract_id=short_contract_id,
        expiration=date(2026, 9, 18),
        debit=Decimal(debit),
        maximum_loss=Decimal(debit) * 100,
        maximum_gain=Decimal("100"),
        break_even=Decimal("101"),
        net_delta=Decimal("0.2"),
        net_gamma=Decimal("0.01"),
        net_theta=Decimal("-0.02"),
        net_vega=Decimal("0.03"),
        liquidity_open_interest=100,
        liquidity_volume=10,
    )


def test_engine_ranks_selectable_spreads_by_maximum_loss_then_contract_identity() -> None:
    result = OptionsAnalysisEngine().rank(
        (_spread("long-b", "short-b", "2"), _spread("long-a", "short-a", "1")),
        blocked_contract_ids=frozenset(),
    )

    assert [item.candidate.long_contract_id for item in result.selectable] == ["long-a", "long-b"]
    assert result.blocked == ()


def test_engine_retains_spreads_with_blocked_leg_outside_selectable_results() -> None:
    result = OptionsAnalysisEngine().rank(
        (_spread("long-a", "short-a", "1"),),
        blocked_contract_ids=frozenset({"short-a"}),
    )

    assert result.selectable == ()
    assert [item.candidate.short_contract_id for item in result.blocked] == ["short-a"]
