from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from market_trader.scanner import RegimeClassifier
from market_trader.scanner.configuration import RegimePolicy
from market_trader.scanner.evidence import (
    BreadthEvidence,
    EvidenceMetadata,
    MacroEvidence,
    MacroState,
    SectorEvidence,
    SectorObservation,
    SupplementalEvidence,
    VolatilityDirection,
    VolatilityEvidence,
)
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import RegimeState

AS_OF = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)
SESSION_DATE = date(2026, 7, 16)
SECTORS = (
    ("XLB", "materials"),
    ("XLC", "communication_services"),
    ("XLE", "energy"),
    ("XLF", "financials"),
    ("XLI", "industrials"),
    ("XLK", "technology"),
    ("XLP", "consumer_staples"),
    ("XLRE", "real_estate"),
    ("XLU", "utilities"),
    ("XLV", "health_care"),
    ("XLY", "consumer_discretionary"),
)
POLICY = RegimePolicy(
    version="market-regime-v1",
    component_weights={
        "broad_trend": Decimal("30"),
        "breadth": Decimal("20"),
        "sector_participation": Decimal("15"),
        "volume_participation": Decimal("10"),
        "volatility_direction": Decimal("15"),
        "macro_overlay": Decimal("10"),
    },
    bullish_total_minimum=Decimal("35"),
    bearish_total_maximum=Decimal("-35"),
    mixed_strategy_minimum_absolute_total=Decimal("20"),
    breadth_bullish_above_sma_fraction=Decimal("0.60"),
    breadth_bearish_above_sma_fraction=Decimal("0.40"),
    participation_bullish_ratio=Decimal("1.50"),
    participation_bearish_ratio=Decimal("0.67"),
    sector_alignment_count=7,
    volatility_change_minimum=Decimal("0.05"),
)


def _metadata(lineage_id: str) -> EvidenceMetadata:
    return EvidenceMetadata(
        schema_version="scanner-evidence-v1",
        configuration_version="fixture-v1",
        correlation_id="regime-test",
        lineage_id=lineage_id,
        source="fixture",
        observed_at=AS_OF - timedelta(minutes=1),
        valid_until=AS_OF,
    )


def _trend(sign: int) -> FeatureResult:
    if sign > 0:
        values = (Decimal("110"), Decimal("105"), Decimal("100"), Decimal("0.01"))
    elif sign < 0:
        values = (Decimal("90"), Decimal("95"), Decimal("100"), Decimal("-0.01"))
    else:
        values = (Decimal("100"), Decimal("100"), Decimal("100"), Decimal("0"))
    return FeatureResult(
        symbol="SPY",
        adjusted_close=values[0],
        sma_50=values[1],
        sma_200=values[2],
        sma_50_slope_20=values[3],
    )


def _breadth(sign: int) -> BreadthEvidence:
    if sign > 0:
        values = (60, 60, 40, Decimal("150"), Decimal("100"))
    elif sign < 0:
        values = (40, 40, 60, Decimal("67"), Decimal("100"))
    else:
        values = (50, 50, 50, Decimal("100"), Decimal("100"))
    return BreadthEvidence(
        **_metadata("breadth-lineage").__dict__,
        source_universe="synthetic-us-equities",
        session_date=SESSION_DATE,
        total_eligible_issues=100,
        advancing_issues=values[1],
        declining_issues=values[2],
        unchanged_issues=0,
        issues_above_sma_50=values[0],
        up_volume=values[3],
        down_volume=values[4],
    )


def _sector(sign: int, *, dispersed: bool = False) -> SectorEvidence:
    observations = []
    for index, (symbol, sector) in enumerate(SECTORS):
        direction = (1 if index < 6 else -1) if dispersed else sign
        relative = Decimal("1") + Decimal(direction) * Decimal("0.1")
        session_return = Decimal(direction) * Decimal("0.01")
        observations.append(
            SectorObservation(
                symbol=symbol,
                sector=sector,
                close_relative_to_sma_50=relative,
                return_20_session=session_return,
            )
        )
    return SectorEvidence(
        **_metadata("sector-lineage").__dict__,
        session_date=SESSION_DATE,
        observations=tuple(observations),
    )


def _volatility(sign: int) -> VolatilityEvidence:
    if sign > 0:
        current, direction = Decimal("19"), VolatilityDirection.FALLING
    elif sign < 0:
        current, direction = Decimal("21"), VolatilityDirection.RISING
    else:
        current, direction = Decimal("20"), VolatilityDirection.FLAT
    return VolatilityEvidence(
        **_metadata("volatility-lineage").__dict__,
        measure="VIX",
        current_value=current,
        value_five_sessions_earlier=Decimal("20"),
        median_20_session=Decimal("20"),
        direction=direction,
    )


def _macro(state: MacroState) -> MacroEvidence:
    return MacroEvidence(
        **_metadata("macro-lineage").__dict__, state=state, reason_codes=()
    )


def _evidence(
    *,
    breadth: tuple[BreadthEvidence, ...] | None = None,
    sector: tuple[SectorEvidence, ...] | None = None,
    volatility: tuple[VolatilityEvidence, ...] | None = None,
    macro: tuple[MacroEvidence, ...] | None = None,
) -> SupplementalEvidence:
    return SupplementalEvidence(
        as_of=AS_OF,
        breadth=(_breadth(0),) if breadth is None else breadth,
        sector=(_sector(0),) if sector is None else sector,
        volatility=(_volatility(0),) if volatility is None else volatility,
        macro=(_macro(MacroState.NEUTRAL),) if macro is None else macro,
        catalysts=(),
    )


@pytest.mark.parametrize(
    ("sign", "macro_state", "expected_state", "expected_score"),
    [
        (1, MacroState.RISK_ON, RegimeState.BULLISH, Decimal("100")),
        (0, MacroState.NEUTRAL, RegimeState.NEUTRAL, Decimal("0")),
        (-1, MacroState.RISK_OFF, RegimeState.BEARISH, Decimal("-100")),
    ],
)
def test_classifies_all_component_signs(
    sign: int,
    macro_state: MacroState,
    expected_state: RegimeState,
    expected_score: Decimal,
) -> None:
    result = RegimeClassifier(POLICY).classify(
        (_trend(sign),),
        _evidence(
            breadth=(_breadth(sign),),
            sector=(_sector(sign),),
            volatility=(_volatility(sign),),
            macro=(_macro(macro_state),),
        ),
    )

    assert result.state is expected_state
    assert result.signed_score == expected_score
    assert result.components == {
        "breadth": Decimal(sign * 20),
        "broad_trend": Decimal(sign * 30),
        "macro_overlay": Decimal(sign * 10),
        "sector_participation": Decimal(sign * 15),
        "volatility_direction": Decimal(sign * 15),
        "volume_participation": Decimal(sign * 10),
    }


@pytest.mark.parametrize(
    ("trend", "volatility", "macro", "state", "score"),
    [
        (1, 1, MacroState.RISK_OFF, RegimeState.BULLISH, Decimal("35")),
        (-1, -1, MacroState.RISK_ON, RegimeState.BEARISH, Decimal("-35")),
    ],
)
def test_classification_thresholds_are_inclusive(
    trend: int,
    volatility: int,
    macro: MacroState,
    state: RegimeState,
    score: Decimal,
) -> None:
    result = RegimeClassifier(POLICY).classify(
        (_trend(trend),),
        _evidence(volatility=(_volatility(volatility),), macro=(_macro(macro),)),
    )

    assert result.state is state
    assert result.signed_score == score


def test_opposing_nonzero_trend_and_breadth_is_mixed() -> None:
    result = RegimeClassifier(POLICY).classify(
        (_trend(1),),
        _evidence(breadth=(_breadth(-1),)),
    )

    assert result.state is RegimeState.MIXED
    assert result.signed_score == Decimal("0")
    assert result.reasons == ("trend_breadth_divergence",)


def test_sector_dispersion_with_fewer_than_seven_aligned_is_mixed() -> None:
    result = RegimeClassifier(POLICY).classify(
        (_trend(0),),
        _evidence(sector=(_sector(0, dispersed=True),)),
    )

    assert result.state is RegimeState.MIXED
    assert result.components["sector_participation"] == Decimal("0")
    assert result.reasons == ("sector_dispersion",)


@pytest.mark.parametrize("family", ["trend", "breadth", "sector", "volatility"])
def test_missing_critical_family_blocks(family: str) -> None:
    features = () if family == "trend" else (_trend(0),)
    changes: dict[str, object] = {}
    if family != "trend":
        changes[family] = ()
    result = RegimeClassifier(POLICY).classify(features, _evidence(**changes))  # type: ignore[arg-type]

    assert result.state is RegimeState.BLOCKED
    assert "regime_input_missing" in result.reasons


@pytest.mark.parametrize("family", ["breadth", "sector", "volatility"])
def test_stale_critical_family_blocks(family: str) -> None:
    record = {"breadth": _breadth(0), "sector": _sector(0), "volatility": _volatility(0)}[
        family
    ]
    stale = replace(record, valid_until=AS_OF - timedelta(microseconds=1))
    result = RegimeClassifier(POLICY).classify(
        (_trend(0),),
        _evidence(**{family: (stale,)}),  # type: ignore[arg-type]
    )

    assert result.state is RegimeState.BLOCKED
    assert "regime_input_stale" in result.reasons


def test_conflicting_critical_inputs_and_macro_block_are_sorted() -> None:
    result = RegimeClassifier(POLICY).classify(
        (_trend(0), _trend(1)),
        _evidence(
            breadth=(_breadth(0), replace(_breadth(1), lineage_id="breadth-other")),
            macro=(_macro(MacroState.BLOCKED),),
        ),
    )

    assert result.state is RegimeState.BLOCKED
    assert result.reasons == ("macro_blocked", "regime_input_conflicting")


def test_zero_breadth_denominator_blocks_without_directional_points() -> None:
    unavailable_ratio = replace(
        _breadth(0),
        advancing_issues=0,
        declining_issues=0,
        unchanged_issues=100,
        issues_above_sma_50=60,
        up_volume=Decimal("0"),
        down_volume=Decimal("0"),
    )
    result = RegimeClassifier(POLICY).classify(
        (_trend(0),),
        _evidence(breadth=(unavailable_ratio,)),
    )

    assert result.state is RegimeState.BLOCKED
    assert result.components["breadth"] == Decimal("0")
    assert result.components["volume_participation"] == Decimal("0")
    assert "regime_input_missing" in result.reasons


def test_positive_zero_denominators_are_bounded_and_explained() -> None:
    zero_denominators = replace(
        _breadth(1),
        advancing_issues=100,
        declining_issues=0,
        up_volume=Decimal("100"),
        down_volume=Decimal("0"),
    )
    result = RegimeClassifier(POLICY).classify(
        (_trend(0),),
        _evidence(breadth=(zero_denominators,)),
    )

    assert result.components["breadth"] == Decimal("20")
    assert result.components["volume_participation"] == Decimal("10")
    assert result.reasons == ("feature_division_by_zero", "no_declining_issues")


def test_missing_macro_and_zero_volatility_baseline_block() -> None:
    zero_baseline = replace(
        _volatility(0),
        current_value=Decimal("0"),
        value_five_sessions_earlier=Decimal("0"),
    )
    result = RegimeClassifier(POLICY).classify(
        (_trend(0),),
        _evidence(volatility=(zero_baseline,), macro=()),
    )

    assert result.state is RegimeState.BLOCKED
    assert result.reasons == ("regime_input_missing",)


def test_malformed_sector_membership_blocks_as_conflicting() -> None:
    malformed = replace(_sector(0), observations=_sector(0).observations[:6])
    result = RegimeClassifier(POLICY).classify(
        (_trend(0),),
        _evidence(sector=(malformed,)),
    )

    assert result.state is RegimeState.BLOCKED
    assert result.reasons == ("regime_input_conflicting",)


def test_ordering_does_not_change_result_or_lineage() -> None:
    sector = _sector(1)
    reversed_sector = replace(sector, observations=tuple(reversed(sector.observations)))
    evidence = _evidence(
        breadth=(_breadth(1),),
        sector=(reversed_sector,),
        volatility=(_volatility(1),),
        macro=(_macro(MacroState.RISK_ON),),
    )
    calculator = RegimeClassifier(POLICY)

    first = calculator.classify((_trend(1), FeatureResult(symbol="QQQ")), evidence)
    second = calculator.classify(
        (FeatureResult(symbol="QQQ"), _trend(1)),
        replace(evidence, sector=(sector,)),
    )

    assert first == second
    assert first.lineage == (
        "breadth-lineage",
        "macro-lineage",
        "sector-lineage",
        "volatility-lineage",
    )
