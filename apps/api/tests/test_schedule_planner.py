from datetime import UTC, date, datetime, timedelta

import pytest

from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_calendar.policy import EntryWindowPolicy
from market_trader.scheduling.models import (
    JobKind,
    RecurringSchedule,
    SessionAnchor,
    SessionOffsetSchedule,
    SessionWindow,
)
from market_trader.scheduling.planner import SchedulePlanner


@pytest.fixture(scope="module")
def planner() -> SchedulePlanner:
    return SchedulePlanner(
        calendar=XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 12, 31)),
        entry_policy=EntryWindowPolicy.v1(),
    )


def scan_schedule() -> RecurringSchedule:
    return RecurringSchedule(
        schedule_id="scan-fixture",
        job_kind=JobKind.SCAN,
        window=SessionWindow.ENTRY,
        interval=timedelta(minutes=5),
        policy_version="scan-schedule-v1",
    )


def test_normal_session_generates_only_entry_window_runs(planner: SchedulePlanner) -> None:
    runs = planner.runs_between(
        scan_schedule(),
        start_exclusive=datetime(2026, 7, 20, 13, 44, tzinfo=UTC),
        end_inclusive=datetime(2026, 7, 20, 19, 30, tzinfo=UTC),
    )

    assert runs[0].scheduled_for == datetime(2026, 7, 20, 13, 45, tzinfo=UTC)
    assert runs[-1].scheduled_for == datetime(2026, 7, 20, 19, 25, tzinfo=UTC)
    assert all(run.scheduled_for < datetime(2026, 7, 20, 19, 30, tzinfo=UTC) for run in runs)


def test_early_close_shortens_recurring_window(planner: SchedulePlanner) -> None:
    runs = planner.runs_between(
        scan_schedule(),
        start_exclusive=datetime(2026, 11, 27, 14, 44, tzinfo=UTC),
        end_inclusive=datetime(2026, 11, 27, 18, 0, tzinfo=UTC),
    )

    assert runs[0].scheduled_for == datetime(2026, 11, 27, 14, 45, tzinfo=UTC)
    assert runs[-1].scheduled_for == datetime(2026, 11, 27, 17, 25, tzinfo=UTC)


def test_close_relative_run_uses_actual_early_close(planner: SchedulePlanner) -> None:
    schedule = SessionOffsetSchedule(
        schedule_id="eod-fixture",
        job_kind=JobKind.END_OF_DAY,
        anchor=SessionAnchor.CLOSE,
        offset=timedelta(minutes=5),
        policy_version="eod-schedule-v1",
    )

    runs = planner.runs_between(
        schedule,
        start_exclusive=datetime(2026, 11, 27, 18, 0, tzinfo=UTC),
        end_inclusive=datetime(2026, 11, 27, 18, 5, tzinfo=UTC),
    )

    assert len(runs) == 1
    assert runs[0].scheduled_for == datetime(2026, 11, 27, 18, 5, tzinfo=UTC)


def test_weekend_interval_generates_no_runs(planner: SchedulePlanner) -> None:
    runs = planner.runs_between(
        scan_schedule(),
        start_exclusive=datetime(2026, 7, 18, 0, 0, tzinfo=UTC),
        end_inclusive=datetime(2026, 7, 19, 23, 59, tzinfo=UTC),
    )

    assert runs == ()


def test_query_is_start_exclusive_and_end_inclusive(planner: SchedulePlanner) -> None:
    runs = planner.runs_between(
        scan_schedule(),
        start_exclusive=datetime(2026, 7, 20, 13, 45, tzinfo=UTC),
        end_inclusive=datetime(2026, 7, 20, 13, 50, tzinfo=UTC),
    )

    assert tuple(run.scheduled_for for run in runs) == (
        datetime(2026, 7, 20, 13, 50, tzinfo=UTC),
    )


def test_delayed_interval_returns_all_expected_runs_in_order(planner: SchedulePlanner) -> None:
    runs = planner.runs_between(
        scan_schedule(),
        start_exclusive=datetime(2026, 7, 20, 13, 44, tzinfo=UTC),
        end_inclusive=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
    )

    assert tuple(run.scheduled_for.minute for run in runs) == (45, 50, 55, 0)


def test_idempotency_keys_are_deterministic(planner: SchedulePlanner) -> None:
    query = {
        "start_exclusive": datetime(2026, 7, 20, 13, 44, tzinfo=UTC),
        "end_inclusive": datetime(2026, 7, 20, 13, 50, tzinfo=UTC),
    }

    first = planner.runs_between(scan_schedule(), **query)
    second = planner.runs_between(scan_schedule(), **query)

    assert first == second
    assert first[0].idempotency_key == second[0].idempotency_key


def test_all_scheduler_job_kinds_are_representable() -> None:
    assert {item.value for item in JobKind} == {"scan", "refresh", "end_of_day", "recovery"}


def test_rejects_invalid_intervals(planner: SchedulePlanner) -> None:
    with pytest.raises(ValueError, match="positive"):
        RecurringSchedule(
            schedule_id="invalid",
            job_kind=JobKind.REFRESH,
            window=SessionWindow.REGULAR,
            interval=timedelta(0),
            policy_version="invalid-v1",
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        planner.runs_between(
            scan_schedule(),
            start_exclusive=datetime(2026, 7, 20, 13, 44),
            end_inclusive=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
        )
