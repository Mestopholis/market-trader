from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType

from market_trader.catalysts.models import (
    CatalystDecision,
    CatalystDirection,
    CatalystPolicyVersions,
    ConfirmationState,
    Materiality,
    RiskState,
)
from market_trader.catalysts.scanner import ScannerCatalystAdapter
from market_trader.scanner.evidence import (
    CatalystDirection as ScannerDirection,
)
from market_trader.scanner.evidence import (
    CatalystMateriality,
    MacroState,
)

AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=UTC)
VERSIONS = CatalystPolicyVersions()


def _decision(
    *,
    symbol: str | None = "AAPL",
    materiality: Materiality = Materiality.MATERIAL,
    direction: CatalystDirection = CatalystDirection.POSITIVE,
    confirmation: ConfirmationState = ConfirmationState.CONFIRMED,
    risk_state: RiskState = RiskState.CLEAR,
    reasons: tuple[str, ...] = (),
    key: str = "decision-1",
) -> CatalystDecision:
    scope = "market" if symbol is None else "symbol"
    risk: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    if risk_state is not RiskState.CLEAR:
        category = "cpi" if symbol is None else "earnings"
        risk = ((category, risk_state.value, ("risk-observation",)),)
    return CatalystDecision(
        decision_key=key,
        scope=scope,
        symbol=symbol,
        as_of=AS_OF,
        materiality=materiality,
        direction=direction,
        confirmation=confirmation,
        risk_state=risk_state,
        reasons=reasons,
        observation_keys=("observation-1", "observation-2"),
        policy_versions=VERSIONS,
        input_digest="a" * 64,
        explanation=MappingProxyType(
            {"lineage": ("observation-1", "observation-2"), "risk": risk}
        ),
    )


def test_confirmed_material_directional_decision_maps_to_news_evidence() -> None:
    result = ScannerCatalystAdapter().adapt((_decision(),), as_of=AS_OF)

    assert len(result.catalysts) == 1
    catalyst = result.catalysts[0]
    assert catalyst.symbol == "AAPL"
    assert catalyst.materiality is CatalystMateriality.MATERIAL
    assert catalyst.direction is ScannerDirection.POSITIVE
    assert catalyst.blocked is False
    assert catalyst.observation_keys == ("observation-1", "observation-2")
    assert catalyst.policy_versions == tuple(VERSIONS.__dict__.values())


def test_changed_decision_changes_deterministic_adapter_output() -> None:
    adapter = ScannerCatalystAdapter()
    decision = _decision()

    first = adapter.adapt((decision,), as_of=AS_OF)
    repeated = adapter.adapt((decision,), as_of=AS_OF)
    changed = adapter.adapt(
        (replace(decision, direction=CatalystDirection.NEGATIVE, input_digest="b" * 64),),
        as_of=AS_OF,
    )

    assert first == repeated
    assert changed != first
    assert decision.direction is CatalystDirection.POSITIVE


def test_conflict_maps_to_blocked_catalyst() -> None:
    result = ScannerCatalystAdapter().adapt(
        (
            _decision(
                direction=CatalystDirection.UNCLEAR,
                confirmation=ConfirmationState.BLOCKED,
                reasons=("conflicting_catalyst_direction",),
            ),
        ),
        as_of=AS_OF,
    )

    assert result.catalysts[0].blocked is True
    assert result.catalysts[0].reason_codes == ("conflicting_catalyst_direction",)


def test_nonconfirmed_or_nondirectional_decisions_cannot_supply_news_evidence() -> None:
    decisions = (
        _decision(confirmation=ConfirmationState.UNCONFIRMED, key="social-only"),
        _decision(materiality=Materiality.CONTEXTUAL, key="contextual"),
        _decision(direction=CatalystDirection.NEUTRAL, key="neutral"),
        _decision(direction=CatalystDirection.UNCLEAR, key="unclear"),
    )

    result = ScannerCatalystAdapter().adapt(decisions, as_of=AS_OF)

    assert result.catalysts == ()


def test_active_earnings_risk_maps_to_symbol_block() -> None:
    result = ScannerCatalystAdapter().adapt(
        (
            _decision(
                confirmation=ConfirmationState.BLOCKED,
                risk_state=RiskState.ACTIVE,
                reasons=("earnings_window_active",),
            ),
        ),
        as_of=AS_OF,
    )

    assert result.catalysts[0].category == "earnings"
    assert result.catalysts[0].blocked is True


def test_unresolved_macro_risk_maps_to_blocked_market_input() -> None:
    result = ScannerCatalystAdapter().adapt(
        (
            _decision(
                symbol=None,
                confirmation=ConfirmationState.BLOCKED,
                risk_state=RiskState.BLOCKED,
                reasons=("macro_schedule_missing",),
            ),
        ),
        as_of=AS_OF,
    )

    assert result.catalysts == ()
    assert len(result.macro) == 1
    assert result.macro[0].state is MacroState.BLOCKED
    assert result.macro[0].reason_codes == ("macro_schedule_missing",)
    assert result.macro[0].observation_keys == (
        "observation-1",
        "observation-2",
        "risk-observation",
    )
