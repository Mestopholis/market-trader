from datetime import UTC, date, datetime, timedelta

import pytest

from market_trader.domain.time import FrozenClock
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.models import DataKind, QualityState
from market_trader.market_data.quality import FreshnessPolicy


@pytest.fixture(scope="module")
def calendar() -> XNYSCalendarAdapter:
    return XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 12, 31))


@pytest.mark.parametrize(
    ("kind", "age", "uses_ingested_at"),
    [
        (DataKind.QUOTE, timedelta(seconds=15), False),
        (DataKind.OPTION_CHAIN, timedelta(seconds=60), False),
        (DataKind.CORPORATE_ACTION, timedelta(hours=24), True),
    ],
)
def test_age_boundaries_are_inclusive(
    calendar: XNYSCalendarAdapter,
    kind: DataKind,
    age: timedelta,
    uses_ingested_at: bool,
) -> None:
    observed = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    ingested = observed + timedelta(seconds=2)
    basis = ingested if uses_ingested_at else observed

    at_boundary = policy_at(calendar, basis + age).evaluate(
        kind,
        observed_at=observed,
        ingested_at=ingested,
    )
    after_boundary = policy_at(calendar, basis + age + timedelta(microseconds=1)).evaluate(
        kind,
        observed_at=observed,
        ingested_at=ingested,
    )

    assert at_boundary.state is QualityState.VALID
    assert after_boundary.state is QualityState.STALE
    assert after_boundary.reason_codes == ("stale",)
    assert after_boundary.blocking is True


def test_one_minute_candle_ages_from_bar_end(calendar: XNYSCalendarAdapter) -> None:
    end = datetime(2026, 7, 17, 14, 31, tzinfo=UTC)

    at_boundary = policy_at(calendar, end + timedelta(seconds=90)).evaluate(
        DataKind.CANDLE,
        observed_at=end,
        ingested_at=end,
        candle_end=end,
    )
    after_boundary = policy_at(
        calendar,
        end + timedelta(seconds=90, microseconds=1),
    ).evaluate(
        DataKind.CANDLE,
        observed_at=end,
        ingested_at=end,
        candle_end=end,
    )

    assert at_boundary.state is QualityState.VALID
    assert after_boundary.state is QualityState.STALE


def test_daily_candle_expires_after_next_session_close_plus_grace(
    calendar: XNYSCalendarAdapter,
) -> None:
    expected = datetime(2026, 7, 6, 20, 1, 30, tzinfo=UTC)
    assessment = policy_at(calendar, expected).evaluate_daily_candle(
        session_date=date(2026, 7, 2)
    )

    assert assessment.state is QualityState.VALID
    assert assessment.valid_until == expected

    stale = policy_at(calendar, expected + timedelta(microseconds=1)).evaluate_daily_candle(
        session_date=date(2026, 7, 2)
    )
    assert stale.state is QualityState.STALE


def test_daily_candle_uses_early_close_from_calendar(calendar: XNYSCalendarAdapter) -> None:
    expected = datetime(2026, 11, 27, 18, 1, 30, tzinfo=UTC)

    assessment = policy_at(calendar, expected).evaluate_daily_candle(
        session_date=date(2026, 11, 25)
    )

    assert assessment.valid_until == expected
    assert assessment.state is QualityState.VALID


def test_future_timestamp_tolerance_is_five_seconds(calendar: XNYSCalendarAdapter) -> None:
    ingested = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)

    allowed = policy_at(calendar, ingested).evaluate(
        DataKind.QUOTE,
        observed_at=ingested + timedelta(seconds=5),
        ingested_at=ingested,
    )
    rejected = policy_at(calendar, ingested).evaluate(
        DataKind.QUOTE,
        observed_at=ingested + timedelta(seconds=5, microseconds=1),
        ingested_at=ingested,
    )

    assert allowed.state is QualityState.VALID
    assert rejected.state is QualityState.QUARANTINED
    assert rejected.reason_codes == ("future_timestamp",)


def test_policy_has_stable_version(calendar: XNYSCalendarAdapter) -> None:
    now = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)
    assert policy_at(calendar, now).version == "market-data-freshness-v1"


def policy_at(calendar: XNYSCalendarAdapter, now: datetime) -> FreshnessPolicy:
    return FreshnessPolicy.v1(calendar=calendar, clock=FrozenClock(now))
