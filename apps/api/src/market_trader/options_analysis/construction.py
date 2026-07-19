from decimal import Decimal

from market_trader.market_data.models import NormalizedOptionContract, PutCall
from market_trader.options_analysis.configuration import OptionsAnalysisPolicy
from market_trader.options_analysis.models import SpreadCandidate, SpreadStrategy


def construct_bull_call_spreads(
    contracts: tuple[NormalizedOptionContract, ...], policy: OptionsAnalysisPolicy
) -> tuple[SpreadCandidate, ...]:
    calls = sorted(
        (contract for contract in contracts if contract.option_type is PutCall.CALL),
        key=lambda contract: (contract.expiration, contract.strike, contract.contract_id),
    )
    candidates: list[SpreadCandidate] = []
    for long_contract in calls:
        for short_contract in calls:
            if long_contract.expiration != short_contract.expiration:
                continue
            if long_contract.strike >= short_contract.strike:
                continue
            debit = long_contract.ask - short_contract.bid
            width = short_contract.strike - long_contract.strike
            if debit <= Decimal(0) or debit >= width:
                continue
            candidates.append(
                SpreadCandidate(
                    strategy=SpreadStrategy.BULL_CALL,
                    long_contract_id=long_contract.contract_id,
                    short_contract_id=short_contract.contract_id,
                    expiration=long_contract.expiration,
                    debit=debit,
                    maximum_loss=debit * policy.contract_multiplier,
                    maximum_gain=(width - debit) * policy.contract_multiplier,
                    break_even=long_contract.strike + debit,
                    net_delta=_greek(long_contract.delta) - _greek(short_contract.delta),
                    net_gamma=_greek(long_contract.gamma) - _greek(short_contract.gamma),
                    net_theta=_greek(long_contract.theta) - _greek(short_contract.theta),
                    net_vega=_greek(long_contract.vega) - _greek(short_contract.vega),
                    liquidity_open_interest=min(
                        _liquidity(long_contract.open_interest),
                        _liquidity(short_contract.open_interest),
                    ),
                    liquidity_volume=min(
                        _liquidity(long_contract.volume), _liquidity(short_contract.volume)
                    ),
                )
            )
    return tuple(candidates)


def construct_bear_put_spreads(
    contracts: tuple[NormalizedOptionContract, ...], policy: OptionsAnalysisPolicy
) -> tuple[SpreadCandidate, ...]:
    puts = sorted(
        (contract for contract in contracts if contract.option_type is PutCall.PUT),
        key=lambda contract: (contract.expiration, contract.strike, contract.contract_id),
    )
    candidates: list[SpreadCandidate] = []
    for long_contract in puts:
        for short_contract in puts:
            if long_contract.expiration != short_contract.expiration:
                continue
            if long_contract.strike <= short_contract.strike:
                continue
            debit = long_contract.ask - short_contract.bid
            width = long_contract.strike - short_contract.strike
            if debit <= Decimal(0) or debit >= width:
                continue
            candidates.append(
                SpreadCandidate(
                    strategy=SpreadStrategy.BEAR_PUT,
                    long_contract_id=long_contract.contract_id,
                    short_contract_id=short_contract.contract_id,
                    expiration=long_contract.expiration,
                    debit=debit,
                    maximum_loss=debit * policy.contract_multiplier,
                    maximum_gain=(width - debit) * policy.contract_multiplier,
                    break_even=long_contract.strike - debit,
                    net_delta=_greek(long_contract.delta) - _greek(short_contract.delta),
                    net_gamma=_greek(long_contract.gamma) - _greek(short_contract.gamma),
                    net_theta=_greek(long_contract.theta) - _greek(short_contract.theta),
                    net_vega=_greek(long_contract.vega) - _greek(short_contract.vega),
                    liquidity_open_interest=min(
                        _liquidity(long_contract.open_interest),
                        _liquidity(short_contract.open_interest),
                    ),
                    liquidity_volume=min(
                        _liquidity(long_contract.volume), _liquidity(short_contract.volume)
                    ),
                )
            )
    return tuple(candidates)


def _greek(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("spread construction requires Greeks")
    return value


def _liquidity(value: int | None) -> int:
    if value is None:
        raise ValueError("spread construction requires liquidity")
    return value
