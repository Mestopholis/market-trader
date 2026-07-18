from datetime import UTC, date, datetime, timedelta

import pytest

from market_trader.domain.time import FrozenClock
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_calendar.models import CalendarUnavailableError, MarketState
from market_trader.market_calendar.policy import EntryWindowPolicy
from market_trader.market_calendar.service import MarketStateService


@pytest.fixture(scope="module")
def calendar() -> XNYSCalendarAdapter:
    return XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 12, 31))


def service_at(
    observed_at: datetime,
    calendar: XNYSCalendarAdapter,
) -> MarketStateService:
    return MarketStateService(
        clock=FrozenClock(observed_at),
        calendar=calendar,
        entry_policy=EntryWindowPolicy.v1(),
        display_timezone="America/Chicago",
    )


@pytest.mark.parametrize(
    ("observed_at", "expected_state", "entry_allowed", "next_transition"),
    [
        (
            datetime(2026, 7, 20, 13, 29, 59, tzinfo=UTC),
            MarketState.PRE_MARKET,
            False,
            datetime(2026, 7, 20, 13, 30, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 20, 13, 30, tzinfo=UTC),
            MarketState.OPENING_BUFFER,
            False,
            datetime(2026, 7, 20, 13, 45, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 20, 13, 45, tzinfo=UTC),
            MarketState.ENTRY_OPEN,
            True,
            datetime(2026, 7, 20, 19, 30, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 20, 19, 30, tzinfo=UTC),
            MarketState.ENTRY_CLOSED,
            False,
            datetime(2026, 7, 20, 20, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 20, 20, 0, tzinfo=UTC),
            MarketState.POST_MARKET,
            False,
            datetime(2026, 7, 21, 13, 30, tzinfo=UTC),
        ),
    ],
)
def test_state_boundaries(
    calendar: XNYSCalendarAdapter,
    observed_at: datetime,
    expected_state: MarketState,
    entry_allowed: bool,
    next_transition: datetime,
) -> None:
    snapshot = service_at(observed_at, calendar).current()

    assert snapshot.market_state is expected_state
    assert snapshot.entry_allowed is entry_allowed
    assert snapshot.next_transition == next_transition


def test_weekend_is_closed_until_next_session(calendar: XNYSCalendarAdapter) -> None:
    snapshot = service_at(datetime(2026, 7, 18, 15, 0, tzinfo=UTC), calendar).current()

    assert snapshot.market_state is MarketState.CLOSED
    assert snapshot.session is None
    assert snapshot.entry_window is None
    assert snapshot.next_session.session_date == date(2026, 7, 20)
    assert snapshot.next_transition == datetime(2026, 7, 20, 13, 30, tzinfo=UTC)


def test_early_close_ends_entry_window_thirty_minutes_before_close(
    calendar: XNYSCalendarAdapter,
) -> None:
    snapshot = service_at(datetime(2026, 11, 27, 17, 30, tzinfo=UTC), calendar).current()

    assert snapshot.market_state is MarketState.ENTRY_CLOSED
    assert not snapshot.entry_allowed
    assert snapshot.entry_window is not None
    assert snapshot.entry_window.closes_at == datetime(2026, 11, 27, 17, 30, tzinfo=UTC)
    assert snapshot.session is not None
    assert snapshot.session.is_early_close


def test_valid_until_uses_sixty_second_freshness_away_from_transition(
    calendar: XNYSCalendarAdapter,
) -> None:
    observed_at = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)
    snapshot = service_at(observed_at, calendar).current()

    assert snapshot.valid_until == observed_at + timedelta(seconds=60)


def test_valid_until_is_capped_at_next_transition(calendar: XNYSCalendarAdapter) -> None:
    snapshot = service_at(datetime(2026, 7, 20, 13, 44, 30, tzinfo=UTC), calendar).current()

    assert snapshot.valid_until == datetime(2026, 7, 20, 13, 45, tzinfo=UTC)


def test_snapshot_freshness_boundary_is_inclusive(calendar: XNYSCalendarAdapter) -> None:
    snapshot = service_at(datetime(2026, 7, 20, 15, 0, tzinfo=UTC), calendar).current()

    assert snapshot.is_fresh(snapshot.valid_until)
    assert not snapshot.is_fresh(snapshot.valid_until + timedelta(microseconds=1))


class FailingCalendar:
    name = "XNYS"
    timezone_name = "America/New_York"

    def is_session(self, session_date: date) -> bool:
        raise CalendarUnavailableError("fixture failure")


class NaiveClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 20, 15, 0)


def test_calendar_failure_is_not_replaced_with_guessed_state() -> None:
    service = MarketStateService(
        clock=FrozenClock(datetime(2026, 7, 20, 15, 0, tzinfo=UTC)),
        calendar=FailingCalendar(),  # type: ignore[arg-type]
        entry_policy=EntryWindowPolicy.v1(),
        display_timezone="America/Chicago",
    )

    with pytest.raises(CalendarUnavailableError, match="fixture failure"):
        service.current()


def test_naive_clock_value_is_rejected_before_calendar_lookup(
    calendar: XNYSCalendarAdapter,
) -> None:
    service = MarketStateService(
        clock=NaiveClock(),
        calendar=calendar,
        entry_policy=EntryWindowPolicy.v1(),
        display_timezone="America/Chicago",
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        service.current()
