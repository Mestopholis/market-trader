from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.evidence import (
    CatalystDirection,
    CatalystEvidence,
    CatalystMateriality,
    SupplementalEvidence,
)
from market_trader.scanner.features import FeatureResult
from market_trader.scanner.models import Direction, RegimeResult, RegimeState, StrategyStatus
from market_trader.scanner.strategies.news import NewsContinuationEvaluator

CONFIGURATION_PATH = Path(__file__).parents[3] / "config" / "scanner"
POLICY = load_scanner_configuration(CONFIGURATION_PATH).strategies
AS_OF = datetime(2026, 7, 17, 15, 35, tzinfo=UTC)
LOOKBACK_CUTOFF = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)


def _catalyst(
    direction: CatalystDirection = CatalystDirection.POSITIVE,
    *,
    lineage_id: str = "catalyst-lineage",
    materiality: CatalystMateriality = CatalystMateriality.MATERIAL,
    published_at: datetime = LOOKBACK_CUTOFF,
    valid_until: datetime = AS_OF,
    source_reference: str = "https://example.test/filing",
) -> CatalystEvidence:
    return CatalystEvidence(
        schema_version="scanner-evidence-v1",
        configuration_version="fixture-v1",
        correlation_id="news-test",
        lineage_id=lineage_id,
        source="fixture",
        observed_at=AS_OF - timedelta(minutes=1),
        valid_until=valid_until,
        evidence_id=f"evidence-{lineage_id}-{direction.value}",
        symbol="AAPL",
        source_reference=source_reference,
        published_at=published_at,
        materiality=materiality,
        direction=direction,
        category="earnings_guidance",
    )


def _evidence(*catalysts: CatalystEvidence) -> SupplementalEvidence:
    return SupplementalEvidence(
        as_of=AS_OF,
        breadth=(),
        sector=(),
        volatility=(),
        macro=(),
        catalysts=catalysts,
    )


def _features(direction: Direction) -> FeatureResult:
    if direction is Direction.BULLISH:
        session_open, session_close, session_vwap = "100", "110", "109"
    else:
        session_open, session_close, session_vwap = "100", "90", "91"
    return FeatureResult(
        symbol="AAPL",
        session_open=Decimal(session_open),
        session_close=Decimal(session_close),
        session_vwap=Decimal(session_vwap),
        relative_volume_20=Decimal("1.50"),
    )


def _regime(state: RegimeState = RegimeState.NEUTRAL, score: str = "0") -> RegimeResult:
    return RegimeResult(
        state=state,
        signed_score=Decimal(score),
        policy_version="market-regime-v1",
        lineage=("regime-lineage",),
    )


@pytest.mark.parametrize(
    ("catalyst_direction", "result_direction"),
    [
        (CatalystDirection.POSITIVE, Direction.BULLISH),
        (CatalystDirection.NEGATIVE, Direction.BEARISH),
    ],
)
def test_positive_and_negative_news_continuation_pass(
    catalyst_direction: CatalystDirection,
    result_direction: Direction,
) -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(result_direction),
        _regime(),
        _evidence(_catalyst(catalyst_direction)),
    )

    assert result.status is StrategyStatus.PASSED
    assert result.direction is result_direction
    assert result.reasons == ()
    assert all(gate.passed is True for gate in result.gates)
    assert result.lineage == ("catalyst-lineage", "regime-lineage")


def test_no_catalyst_is_not_applicable() -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH), _regime(), _evidence()
    )

    assert result.status is StrategyStatus.NOT_APPLICABLE
    assert result.reasons == ("catalyst_missing",)


def test_non_material_is_not_applicable_but_unclear_material_fails() -> None:
    evaluator = NewsContinuationEvaluator(POLICY)
    non_material = evaluator.evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(_catalyst(materiality=CatalystMateriality.NON_MATERIAL)),
    )
    unclear = evaluator.evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(_catalyst(CatalystDirection.UNCLEAR)),
    )

    assert non_material.status is StrategyStatus.NOT_APPLICABLE
    assert non_material.reasons == ("catalyst_not_material",)
    assert unclear.status is StrategyStatus.FAILED
    assert unclear.reasons == ("catalyst_direction_unclear",)


def test_clear_material_catalyst_is_not_vetoed_by_unclear_evidence() -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(
            _catalyst(lineage_id="clear"),
            _catalyst(CatalystDirection.UNCLEAR, lineage_id="unclear"),
        ),
    )

    assert result.status is StrategyStatus.PASSED
    assert result.direction is Direction.BULLISH


@pytest.mark.parametrize(
    "catalyst",
    [
        _catalyst(valid_until=AS_OF - timedelta(microseconds=1)),
        _catalyst(published_at=LOOKBACK_CUTOFF - timedelta(microseconds=1)),
    ],
)
def test_stale_or_out_of_lookback_catalyst_blocks(catalyst: CatalystEvidence) -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH), _regime(), _evidence(catalyst)
    )

    assert result.status is StrategyStatus.BLOCKED
    assert result.reasons == ("catalyst_stale",)


def test_missing_attribution_blocks() -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(_catalyst(source_reference="")),
    )

    assert result.status is StrategyStatus.BLOCKED
    assert result.reasons == ("catalyst_missing",)


def test_identical_duplicate_lineage_counts_once_and_is_explained() -> None:
    catalyst = _catalyst()
    duplicate = replace(catalyst, evidence_id="duplicate-evidence")
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(duplicate, catalyst),
    )

    assert result.status is StrategyStatus.PASSED
    assert result.reasons == ("duplicate_evidence_lineage",)
    assert result.lineage.count("catalyst-lineage") == 1


def test_conflicting_duplicate_lineage_blocks_before_direction_conflict() -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(
            _catalyst(CatalystDirection.POSITIVE),
            _catalyst(CatalystDirection.NEGATIVE),
        ),
    )

    assert result.status is StrategyStatus.BLOCKED
    assert result.reasons == ("duplicate_evidence_lineage",)


def test_independent_positive_and_negative_catalysts_block() -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(
            _catalyst(CatalystDirection.POSITIVE, lineage_id="positive"),
            _catalyst(CatalystDirection.NEGATIVE, lineage_id="negative"),
        ),
    )

    assert result.status is StrategyStatus.BLOCKED
    assert result.reasons == ("conflicting_catalyst_direction",)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"relative_volume_20": Decimal("1.49")}, "relative_volume_below_minimum"),
        ({"session_vwap": Decimal("110")}, "price_below_vwap"),
        ({"session_open": Decimal("110")}, "session_open_not_held"),
    ],
)
def test_positive_directional_gate_failures(changes: dict[str, object], reason: str) -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        replace(_features(Direction.BULLISH), **changes),  # type: ignore[arg-type]
        _regime(),
        _evidence(_catalyst()),
    )

    assert result.status is StrategyStatus.FAILED
    assert reason in result.reasons


@pytest.mark.parametrize(
    ("direction", "score", "status"),
    [
        (Direction.BULLISH, "-35", StrategyStatus.FAILED),
        (Direction.BULLISH, "-34.999999", StrategyStatus.PASSED),
        (Direction.BEARISH, "35", StrategyStatus.FAILED),
        (Direction.BEARISH, "34.999999", StrategyStatus.PASSED),
    ],
)
def test_opposing_regime_boundary_is_exact(
    direction: Direction, score: str, status: StrategyStatus
) -> None:
    catalyst_direction = (
        CatalystDirection.POSITIVE if direction is Direction.BULLISH else CatalystDirection.NEGATIVE
    )
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(direction),
        _regime(score=score),
        _evidence(_catalyst(catalyst_direction)),
    )

    assert result.status is status


def test_blocked_regime_blocks_news() -> None:
    result = NewsContinuationEvaluator(POLICY).evaluate(
        _features(Direction.BULLISH),
        _regime(RegimeState.BLOCKED),
        _evidence(_catalyst()),
    )

    assert result.status is StrategyStatus.BLOCKED
    assert "regime_blocked" in result.reasons


def test_input_order_does_not_change_result() -> None:
    first_catalyst = _catalyst(lineage_id="a")
    second_catalyst = _catalyst(lineage_id="z")
    evaluator = NewsContinuationEvaluator(POLICY)

    first = evaluator.evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(first_catalyst, second_catalyst),
    )
    second = evaluator.evaluate(
        _features(Direction.BULLISH),
        _regime(),
        _evidence(second_catalyst, first_catalyst),
    )

    assert first == second
