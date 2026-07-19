from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_trader.catalysts.configuration import load_catalyst_configuration
from market_trader.catalysts.models import (
    AuthorityClass,
    CatalystObservation,
    EventFamily,
    RiskState,
)
from market_trader.catalysts.risk import EventRiskEvaluator, display_risk_bounds
from market_trader.market_calendar.adapter import XNYSCalendarAdapter

API_ROOT = Path(__file__).parents[2]
CONFIGURATION = load_catalyst_configuration(API_ROOT / "config" / "catalysts")
POLICY = CONFIGURATION.risk
NY = ZoneInfo("America/New_York")
CHICAGO = ZoneInfo("America/Chicago")


@pytest.fixture
def evaluator() -> EventRiskEvaluator:
    return EventRiskEvaluator(
        calendar=XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 12, 31)),
        policy=POLICY,
    )


def _schedule(
    scheduled_for: datetime | None,
    *,
    category: str = "earnings_schedule",
    family: EventFamily = EventFamily.EARNINGS,
    symbol: str | None = "AAPL",
    key: str = "obs-schedule-1",
    valid_until: datetime | None = None,
    timing: str = "unknown",
) -> CatalystObservation:
    observed = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    return CatalystObservation(
        observation_key=key,
        ingestion_key=f"ing-{key}",
        authoritative_digest="a" * 64,
        external_text_digest="b" * 64,
        source_id="fixture",
        authority_class=AuthorityClass.AUTHORIZED_STRUCTURED,
        event_family=family,
        event_category=category,
        provider_event_id=key,
        source_reference=f"fixture://{key}",
        symbol=symbol,
        published_at=observed,
        ingested_at=observed,
        scheduled_for=scheduled_for,
        valid_until=valid_until or datetime(2027, 1, 1, tzinfo=UTC),
        structured_facts={"event_category": category, "session_timing": timing},
        external_text={},
        source_schema_version=1,
        normalization_schema_version=1,
        configuration_version="catalyst-source-policy-v1",
        correlation_id=f"corr-{key}",
    )


@pytest.mark.parametrize("timing", ("before_market", "after_market", "unknown"))
def test_earnings_window_uses_two_prior_sessions_and_full_post_session(
    evaluator: EventRiskEvaluator,
    timing: str,
) -> None:
    scheduled = datetime(2026, 7, 17, 8, 0, tzinfo=NY)
    observation = _schedule(scheduled, timing=timing)

    window = evaluator.evaluate_earnings(
        "AAPL",
        (observation,),
        as_of=datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
    )

    assert window.starts_at == datetime(2026, 7, 15, 13, 30, tzinfo=UTC)
    assert window.ends_at == datetime(2026, 7, 20, 20, 0, tzinfo=UTC)
    assert window.state is RiskState.ACTIVE
    assert window.reasons == ("earnings_window_active",)
    assert window.lineage == ("obs-schedule-1",)


@pytest.mark.parametrize(
    ("scheduled", "expected_start", "expected_end"),
    (
        (
            datetime(2026, 7, 18, 8, 0, tzinfo=NY),
            datetime(2026, 7, 16, 13, 30, tzinfo=UTC),
            datetime(2026, 7, 21, 20, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 3, 8, 0, tzinfo=NY),
            datetime(2026, 7, 1, 13, 30, tzinfo=UTC),
            datetime(2026, 7, 7, 20, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 3, 10, 8, 0, tzinfo=NY),
            datetime(2026, 3, 6, 14, 30, tzinfo=UTC),
            datetime(2026, 3, 11, 20, 0, tzinfo=UTC),
        ),
    ),
)
def test_earnings_window_traverses_weekends_holidays_and_dst(
    evaluator: EventRiskEvaluator,
    scheduled: datetime,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    window = evaluator.evaluate_earnings(
        "AAPL",
        (_schedule(scheduled),),
        as_of=expected_start,
    )

    assert window.starts_at == expected_start
    assert window.ends_at == expected_end


def test_earnings_post_session_skips_early_close(evaluator: EventRiskEvaluator) -> None:
    scheduled = datetime(2026, 11, 25, 16, 30, tzinfo=NY)

    window = evaluator.evaluate_earnings(
        "AAPL",
        (_schedule(scheduled, timing="after_market"),),
        as_of=datetime(2026, 11, 25, 20, 0, tzinfo=UTC),
    )

    assert window.ends_at == datetime(2026, 11, 30, 21, 0, tzinfo=UTC)


def test_earnings_bounds_are_inclusive(evaluator: EventRiskEvaluator) -> None:
    observation = _schedule(datetime(2026, 7, 17, 8, 0, tzinfo=NY))
    active_start = evaluator.evaluate_earnings(
        "AAPL",
        (observation,),
        as_of=datetime(2026, 7, 15, 13, 30, tzinfo=UTC),
    )
    before = evaluator.evaluate_earnings(
        "AAPL",
        (observation,),
        as_of=datetime(2026, 7, 15, 13, 30, tzinfo=UTC) - timedelta(microseconds=1),
    )
    active_end = evaluator.evaluate_earnings(
        "AAPL",
        (observation,),
        as_of=datetime(2026, 7, 20, 20, 0, tzinfo=UTC),
    )
    after = evaluator.evaluate_earnings(
        "AAPL",
        (observation,),
        as_of=datetime(2026, 7, 20, 20, 0, tzinfo=UTC) + timedelta(microseconds=1),
    )

    assert active_start.state is RiskState.ACTIVE
    assert active_end.state is RiskState.ACTIVE
    assert before.state is RiskState.CLEAR
    assert after.state is RiskState.CLEAR


def test_missing_stale_and_conflicting_earnings_timing_block(
    evaluator: EventRiskEvaluator,
) -> None:
    as_of = datetime(2026, 7, 16, 15, 0, tzinfo=UTC)
    missing = evaluator.evaluate_earnings("AAPL", (), as_of=as_of)
    stale = evaluator.evaluate_earnings(
        "AAPL",
        (
            _schedule(
                datetime(2026, 7, 17, 8, 0, tzinfo=NY),
                valid_until=as_of - timedelta(microseconds=1),
            ),
        ),
        as_of=as_of,
    )
    conflicting = evaluator.evaluate_earnings(
        "AAPL",
        (
            _schedule(datetime(2026, 7, 17, 8, 0, tzinfo=NY), key="obs-1"),
            _schedule(datetime(2026, 7, 18, 8, 0, tzinfo=NY), key="obs-2"),
        ),
        as_of=as_of,
    )

    assert missing.state is RiskState.BLOCKED
    assert missing.reasons == ("earnings_time_missing",)
    assert stale.state is RiskState.BLOCKED
    assert stale.reasons == ("earnings_time_missing",)
    assert conflicting.state is RiskState.BLOCKED
    assert conflicting.reasons == ("earnings_time_conflicting",)


def test_earnings_rejects_naive_as_of(evaluator: EventRiskEvaluator) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluator.evaluate_earnings(
            "AAPL",
            (_schedule(datetime(2026, 7, 17, 8, 0, tzinfo=NY)),),
            as_of=datetime(2026, 7, 16, 10, 0),
        )


@pytest.mark.parametrize(
    "category",
    ("consumer_price_index", "employment_situation", "fomc_rate_decision"),
)
def test_high_impact_macro_window_uses_sixty_before_thirty_after(
    evaluator: EventRiskEvaluator,
    category: str,
) -> None:
    scheduled = datetime(2026, 7, 14, 8, 30, tzinfo=NY)
    observation = _schedule(
        scheduled,
        category=category,
        family=EventFamily.ECONOMIC_RELEASE,
        symbol=None,
    )

    window = evaluator.evaluate_macro(
        category,
        (observation,),
        as_of=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
    )

    assert window.starts_at == datetime(2026, 7, 14, 11, 30, tzinfo=UTC)
    assert window.ends_at == datetime(2026, 7, 14, 13, 0, tzinfo=UTC)
    assert window.state is RiskState.ACTIVE
    assert window.reasons == ("macro_window_active",)


def test_macro_bounds_are_inclusive(evaluator: EventRiskEvaluator) -> None:
    category = "consumer_price_index"
    observation = _schedule(
        datetime(2026, 7, 14, 8, 30, tzinfo=NY),
        category=category,
        family=EventFamily.ECONOMIC_RELEASE,
        symbol=None,
    )
    start = datetime(2026, 7, 14, 11, 30, tzinfo=UTC)
    end = datetime(2026, 7, 14, 13, 0, tzinfo=UTC)

    states = tuple(
        evaluator.evaluate_macro(category, (observation,), as_of=value).state
        for value in (
            start - timedelta(microseconds=1),
            start,
            end,
            end + timedelta(microseconds=1),
        )
    )

    assert states == (RiskState.CLEAR, RiskState.ACTIVE, RiskState.ACTIVE, RiskState.CLEAR)


def test_lower_impact_macro_is_clear(evaluator: EventRiskEvaluator) -> None:
    window = evaluator.evaluate_macro(
        "retail_sales",
        (
            _schedule(
                datetime(2026, 7, 14, 8, 30, tzinfo=NY),
                category="retail_sales",
                family=EventFamily.ECONOMIC_RELEASE,
                symbol=None,
            ),
        ),
        as_of=datetime(2026, 7, 14, 12, 30, tzinfo=UTC),
    )

    assert window.state is RiskState.CLEAR
    assert window.starts_at is None
    assert window.ends_at is None


def test_missing_and_conflicting_macro_schedule_block(evaluator: EventRiskEvaluator) -> None:
    category = "consumer_price_index"
    as_of = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    missing = evaluator.evaluate_macro(category, (), as_of=as_of)
    conflicting = evaluator.evaluate_macro(
        category,
        (
            _schedule(
                datetime(2026, 7, 14, 8, 30, tzinfo=NY),
                category=category,
                family=EventFamily.ECONOMIC_RELEASE,
                symbol=None,
                key="obs-1",
            ),
            _schedule(
                datetime(2026, 7, 14, 9, 30, tzinfo=NY),
                category=category,
                family=EventFamily.ECONOMIC_RELEASE,
                symbol=None,
                key="obs-2",
            ),
        ),
        as_of=as_of,
    )

    assert missing.state is RiskState.BLOCKED
    assert missing.reasons == ("macro_schedule_missing",)
    assert conflicting.state is RiskState.BLOCKED
    assert conflicting.reasons == ("macro_schedule_conflicting",)


def test_chicago_display_conversion_does_not_mutate_window_identity(
    evaluator: EventRiskEvaluator,
) -> None:
    category = "consumer_price_index"
    observation = _schedule(
        datetime(2026, 7, 14, 8, 30, tzinfo=NY),
        category=category,
        family=EventFamily.ECONOMIC_RELEASE,
        symbol=None,
    )
    window = evaluator.evaluate_macro(
        category,
        (observation,),
        as_of=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
    )
    original = replace(window)

    displayed = display_risk_bounds(window, "America/Chicago")

    assert displayed == (
        datetime(2026, 7, 14, 6, 30, tzinfo=CHICAGO),
        datetime(2026, 7, 14, 8, 0, tzinfo=CHICAGO),
    )
    assert window == original

