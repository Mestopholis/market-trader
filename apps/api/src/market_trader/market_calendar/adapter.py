from datetime import date, datetime
from typing import Any

import exchange_calendars  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from exchange_calendars import errors as calendar_errors

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.models import (
    CalendarUnavailableError,
    ExchangeSession,
    SessionNotFoundError,
)


class XNYSCalendarAdapter:
    name = "XNYS"
    timezone_name = "America/New_York"

    def __init__(self, *, start: date, end: date) -> None:
        if start >= end:
            raise ValueError("calendar start must be before end")
        self._start = start
        self._end = end
        try:
            self._calendar: Any = exchange_calendars.get_calendar(
                self.name,
                start=start.isoformat(),
                end=end.isoformat(),
            )
        except (calendar_errors.CalendarError, ValueError) as error:
            raise CalendarUnavailableError("XNYS calendar could not be initialized") from error

    def is_session(self, session_date: date) -> bool:
        self._require_date_in_bounds(session_date)
        try:
            return bool(self._calendar.is_session(session_date.isoformat()))
        except calendar_errors.CalendarError as error:
            raise CalendarUnavailableError("XNYS session lookup failed") from error

    def session(self, session_date: date) -> ExchangeSession:
        self._require_date_in_bounds(session_date)
        try:
            market_open = self._calendar.session_open(session_date.isoformat())
            market_close = self._calendar.session_close(session_date.isoformat())
        except calendar_errors.NotSessionError as error:
            raise SessionNotFoundError(
                f"{session_date.isoformat()} is not an XNYS session"
            ) from error
        except calendar_errors.CalendarError as error:
            raise CalendarUnavailableError("XNYS session lookup failed") from error
        return ExchangeSession(
            calendar=self.name,
            session_date=session_date,
            market_open=self._timestamp_to_utc(market_open),
            market_close=self._timestamp_to_utc(market_close),
            is_early_close=pd.Timestamp(session_date) in self._calendar.early_closes,
        )

    def next_session(self, after: date) -> ExchangeSession:
        self._require_date_in_bounds(after)
        try:
            if self._calendar.is_session(after.isoformat()):
                label = self._calendar.next_session(after.isoformat())
            else:
                label = self._calendar.date_to_session(after.isoformat(), direction="next")
        except (calendar_errors.CalendarError, ValueError) as error:
            raise CalendarUnavailableError(
                "next XNYS session is outside supported range"
            ) from error
        return self.session(self._timestamp_to_date(label))

    def previous_session(self, before: date) -> ExchangeSession:
        self._require_date_in_bounds(before)
        try:
            if self._calendar.is_session(before.isoformat()):
                label = self._calendar.previous_session(before.isoformat())
            else:
                label = self._calendar.date_to_session(before.isoformat(), direction="previous")
        except (calendar_errors.CalendarError, ValueError) as error:
            raise CalendarUnavailableError(
                "previous XNYS session is outside supported range"
            ) from error
        return self.session(self._timestamp_to_date(label))

    def sessions_between(self, start: date, end: date) -> tuple[ExchangeSession, ...]:
        self._require_date_in_bounds(start)
        self._require_date_in_bounds(end)
        if start > end:
            raise ValueError("session range start must not be after end")
        try:
            labels = self._calendar.sessions_in_range(start.isoformat(), end.isoformat())
        except calendar_errors.CalendarError as error:
            raise CalendarUnavailableError("XNYS session range lookup failed") from error
        return tuple(self.session(self._timestamp_to_date(label)) for label in labels)

    def session_for_timestamp(self, value: datetime) -> ExchangeSession | None:
        observed_at = ensure_utc(value)
        observed_date = observed_at.astimezone(self._calendar.tz).date()
        self._require_date_in_bounds(observed_date)
        try:
            label = self._calendar.minute_to_session(pd.Timestamp(observed_at), direction="none")
        except ValueError:
            return None
        except calendar_errors.CalendarError as error:
            raise CalendarUnavailableError("XNYS timestamp lookup failed") from error
        return self.session(self._timestamp_to_date(label))

    def _require_date_in_bounds(self, value: date) -> None:
        if value < self._start or value > self._end:
            raise CalendarUnavailableError("date is outside supported range for XNYS calendar")

    @staticmethod
    def _timestamp_to_utc(value: Any) -> datetime:
        converted = value.to_pydatetime()
        if not isinstance(converted, datetime):
            raise CalendarUnavailableError("XNYS returned an invalid timestamp")
        return ensure_utc(converted)

    @staticmethod
    def _timestamp_to_date(value: Any) -> date:
        converted = value.date()
        if not isinstance(converted, date):
            raise CalendarUnavailableError("XNYS returned an invalid session date")
        return converted
