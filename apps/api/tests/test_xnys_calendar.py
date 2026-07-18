from datetime import UTC, date, datetime

import pytest

from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_calendar.models import CalendarUnavailableError, SessionNotFoundError


@pytest.fixture(scope="module")
def calendar() -> XNYSCalendarAdapter:
    return XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 12, 31))


def test_normal_session_uses_expected_utc_hours(calendar: XNYSCalendarAdapter) -> None:
    observed = calendar.session(date(2026, 7, 20))

    assert observed.market_open == datetime(2026, 7, 20, 13, 30, tzinfo=UTC)
    assert observed.market_close == datetime(2026, 7, 20, 20, 0, tzinfo=UTC)
    assert not observed.is_early_close


def test_independence_day_observed_is_not_a_session(calendar: XNYSCalendarAdapter) -> None:
    assert not calendar.is_session(date(2026, 7, 3))

    with pytest.raises(SessionNotFoundError):
        calendar.session(date(2026, 7, 3))


def test_weekend_is_not_a_session(calendar: XNYSCalendarAdapter) -> None:
    assert not calendar.is_session(date(2026, 7, 18))


def test_day_after_thanksgiving_is_early_close(calendar: XNYSCalendarAdapter) -> None:
    observed = calendar.session(date(2026, 11, 27))

    assert observed.market_close == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    assert observed.is_early_close


def test_spring_dst_changes_open_utc_hour(calendar: XNYSCalendarAdapter) -> None:
    assert calendar.session(date(2026, 3, 6)).market_open.hour == 14
    assert calendar.session(date(2026, 3, 9)).market_open.hour == 13


def test_previous_and_next_session_skip_weekend(calendar: XNYSCalendarAdapter) -> None:
    assert calendar.previous_session(date(2026, 7, 20)).session_date == date(2026, 7, 17)
    assert calendar.next_session(date(2026, 7, 17)).session_date == date(2026, 7, 20)


def test_sessions_between_returns_only_sessions(calendar: XNYSCalendarAdapter) -> None:
    observed = calendar.sessions_between(date(2026, 7, 17), date(2026, 7, 21))

    assert tuple(item.session_date for item in observed) == (
        date(2026, 7, 17),
        date(2026, 7, 20),
        date(2026, 7, 21),
    )


def test_timestamp_lookup_returns_session_only_during_regular_hours(
    calendar: XNYSCalendarAdapter,
) -> None:
    observed = calendar.session_for_timestamp(datetime(2026, 7, 20, 15, 0, tzinfo=UTC))

    assert observed is not None
    assert observed.session_date == date(2026, 7, 20)
    assert calendar.session_for_timestamp(datetime(2026, 7, 20, 12, 0, tzinfo=UTC)) is None


def test_timestamp_lookup_rejects_naive_value(calendar: XNYSCalendarAdapter) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        calendar.session_for_timestamp(datetime(2026, 7, 20, 15, 0))


def test_out_of_bounds_lookup_is_translated(calendar: XNYSCalendarAdapter) -> None:
    with pytest.raises(CalendarUnavailableError, match="outside supported range"):
        calendar.session(date(2028, 1, 3))

    with pytest.raises(CalendarUnavailableError, match="outside supported range"):
        calendar.next_session(date(2027, 12, 31))
