from __future__ import annotations

from market_trader.risk.configuration import RiskPolicy
from market_trader.risk.models import (
    ClosedTradeLot,
    RiskCheck,
    RiskCheckSeverity,
    RiskCheckState,
    RiskInput,
    TaxLot,
)


def evaluate_tax_warnings(risk_input: RiskInput, policy: RiskPolicy) -> tuple[RiskCheck, ...]:
    checks = [
        check
        for check in (
            _wash_sale_warning(risk_input, policy),
            _short_term_holding_period_warning(risk_input, policy),
            _long_term_holding_period_warning(risk_input, policy),
        )
        if check is not None
    ]
    return tuple(sorted(checks, key=lambda check: check.code))


def _wash_sale_warning(risk_input: RiskInput, policy: RiskPolicy) -> RiskCheck | None:
    equivalent_symbols = _equivalent_symbols(risk_input.proposal.symbol, policy)
    matching_lots = tuple(
        lot
        for lot in risk_input.closed_trade_lots
        if lot.account_taxable
        and lot.loss_amount > 0
        and lot.symbol in equivalent_symbols
        and 0 <= (risk_input.as_of - lot.closed_at).days <= policy.wash_sale_window_days
    )
    if not matching_lots:
        return None
    return _warning(
        code="tax.wash_sale",
        message="recent taxable loss may create a wash-sale warning",
        matching_lots=matching_lots,
        policy=policy,
        extra_facts={"window_days": policy.wash_sale_window_days},
    )


def _short_term_holding_period_warning(
    risk_input: RiskInput,
    policy: RiskPolicy,
) -> RiskCheck | None:
    matching_lots = tuple(
        lot
        for lot in _matching_open_tax_lots(risk_input, policy)
        if (risk_input.as_of - lot.opened_at).days < policy.short_term_holding_period_days
    )
    if not matching_lots:
        return None
    return _warning(
        code="tax.short_term_holding_period",
        message="taxable lot is inside the short-term holding-period window",
        matching_lots=matching_lots,
        policy=policy,
        extra_facts={"threshold_days": policy.short_term_holding_period_days},
    )


def _long_term_holding_period_warning(
    risk_input: RiskInput,
    policy: RiskPolicy,
) -> RiskCheck | None:
    matching_lots = tuple(
        lot
        for lot in _matching_open_tax_lots(risk_input, policy)
        if policy.short_term_holding_period_days
        <= (risk_input.as_of - lot.opened_at).days
        < policy.long_term_holding_period_days
    )
    if not matching_lots:
        return None
    return _warning(
        code="tax.long_term_holding_period",
        message="taxable lot is near the long-term holding-period boundary",
        matching_lots=matching_lots,
        policy=policy,
        extra_facts={"threshold_days": policy.long_term_holding_period_days},
    )


def _matching_open_tax_lots(risk_input: RiskInput, policy: RiskPolicy) -> tuple[TaxLot, ...]:
    equivalent_symbols = _equivalent_symbols(risk_input.proposal.symbol, policy)
    return tuple(
        lot
        for lot in risk_input.open_tax_lots
        if lot.account_taxable and lot.symbol in equivalent_symbols
    )


def _equivalent_symbols(symbol: str, policy: RiskPolicy) -> frozenset[str]:
    normalized = symbol.upper()
    matches = {normalized}
    for group in policy.equivalent_symbol_groups:
        if normalized in group:
            matches.update(group)
    return frozenset(matches)


def _warning(
    *,
    code: str,
    message: str,
    matching_lots: tuple[TaxLot | ClosedTradeLot, ...],
    policy: RiskPolicy,
    extra_facts: dict[str, object],
) -> RiskCheck:
    lot_keys = tuple(lot.lot_key for lot in matching_lots)
    return RiskCheck(
        code=code,
        severity=RiskCheckSeverity.WARNING,
        state=RiskCheckState.WARNING,
        message=f"{message}; {policy.tax_disclaimer}",
        facts={
            "disclaimer": policy.tax_disclaimer,
            "matching_lots": lot_keys,
            **extra_facts,
        },
        source_keys=lot_keys,
    )
