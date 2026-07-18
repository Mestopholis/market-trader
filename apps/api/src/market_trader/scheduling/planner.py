from datetime import datetime, timedelta
from hashlib import sha256
from math import ceil
from zoneinfo import ZoneInfo

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.models import ExchangeCalendar, ExchangeSession
from market_trader.market_calendar.policy import EntryWindowPolicy
from market_trader.scheduling.models import (
    RecurringSchedule,
    ScheduleDefinition,
    ScheduledRun,
    SessionAnchor,
    SessionOffsetSchedule,
    SessionWindow,
)


class SchedulePlanner:
    def __init__(
        self,
        *,
        calendar: ExchangeCalendar,
        entry_policy: EntryWindowPolicy,
    ) -> None:
        self._calendar = calendar
        self._entry_policy = entry_policy
        self._exchange_timezone = ZoneInfo(calendar.timezone_name)

    def runs_between(
        self,
        definition: ScheduleDefinition,
        *,
        start_exclusive: datetime,
        end_inclusive: datetime,
    ) -> tuple[ScheduledRun, ...]:
        start = ensure_utc(start_exclusive)
        end = ensure_utc(end_inclusive)
        if start >= end:
            raise ValueError("schedule query start must be before end")

        padding = self._padding_for(definition)
        first_date = (start - padding).astimezone(self._exchange_timezone).date()
        last_date = (end + padding).astimezone(self._exchange_timezone).date()
        sessions = self._calendar.sessions_between(first_date, last_date)

        candidates: list[ScheduledRun] = []
        for session in sessions:
            for scheduled_for in self._times_for(definition, session):
                if start < scheduled_for <= end:
                    candidates.append(self._run(definition, session, scheduled_for))
        return tuple(sorted(candidates, key=lambda run: run.scheduled_for))

    def _times_for(
        self,
        definition: ScheduleDefinition,
        session: ExchangeSession,
    ) -> tuple[datetime, ...]:
        if isinstance(definition, SessionOffsetSchedule):
            anchor = (
                session.market_open
                if definition.anchor is SessionAnchor.OPEN
                else session.market_close
            )
            return (anchor + definition.offset,)

        if definition.window is SessionWindow.ENTRY:
            window = self._entry_policy.window_for(session)
            window_start, window_end = window.opens_at, window.closes_at
        else:
            window_start, window_end = session.market_open, session.market_close

        scheduled: list[datetime] = []
        current = window_start
        while current < window_end:
            scheduled.append(current)
            current += definition.interval
        return tuple(scheduled)

    def _run(
        self,
        definition: ScheduleDefinition,
        session: ExchangeSession,
        scheduled_for: datetime,
    ) -> ScheduledRun:
        canonical = "|".join(
            (
                definition.schedule_id,
                definition.policy_version,
                session.calendar,
                session.session_date.isoformat(),
                scheduled_for.isoformat(),
            )
        )
        digest = sha256(canonical.encode()).hexdigest()
        return ScheduledRun(
            schedule_id=definition.schedule_id,
            job_kind=definition.job_kind,
            session_date=session.session_date,
            scheduled_for=scheduled_for,
            calendar=session.calendar,
            policy_version=definition.policy_version,
            idempotency_key=f"run_{digest}",
        )

    @staticmethod
    def _padding_for(definition: ScheduleDefinition) -> timedelta:
        if isinstance(definition, RecurringSchedule):
            return timedelta(days=1)
        seconds_per_day = timedelta(days=1).total_seconds()
        offset_days = ceil(abs(definition.offset.total_seconds()) / seconds_per_day)
        return timedelta(days=offset_days + 1)
