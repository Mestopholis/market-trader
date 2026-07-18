from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_trader.domain.time import Clock
from market_trader.market_calendar.models import (
    EntryWindow,
    ExchangeCalendar,
    ExchangeSession,
    MarketState,
    MarketStateSnapshot,
)
from market_trader.market_calendar.policy import EntryWindowPolicy


class MarketStateService:
    def __init__(
        self,
        *,
        clock: Clock,
        calendar: ExchangeCalendar,
        entry_policy: EntryWindowPolicy,
        display_timezone: str,
        freshness_interval: timedelta = timedelta(seconds=60),
    ) -> None:
        if freshness_interval <= timedelta(0):
            raise ValueError("freshness interval must be positive")
        self._clock = clock
        self._calendar = calendar
        self._entry_policy = entry_policy
        self._display_timezone = display_timezone
        self._freshness_interval = freshness_interval
        self._exchange_timezone = ZoneInfo(calendar.timezone_name)
        ZoneInfo(display_timezone)

    def current(self) -> MarketStateSnapshot:
        observed_at = self._clock.now()
        exchange_date = observed_at.astimezone(self._exchange_timezone).date()

        if not self._calendar.is_session(exchange_date):
            next_session = self._calendar.next_session(exchange_date)
            return self._snapshot(
                state=MarketState.CLOSED,
                observed_at=observed_at,
                next_transition=next_session.market_open,
                session=None,
                entry_window=None,
                next_session=next_session,
            )

        session = self._calendar.session(exchange_date)
        entry_window = self._entry_policy.window_for(session)
        next_session = self._calendar.next_session(exchange_date)
        state, next_transition = self._state_and_transition(
            observed_at,
            session,
            entry_window,
            next_session,
        )
        return self._snapshot(
            state=state,
            observed_at=observed_at,
            next_transition=next_transition,
            session=session,
            entry_window=entry_window,
            next_session=next_session,
        )

    def _snapshot(
        self,
        *,
        state: MarketState,
        observed_at: datetime,
        next_transition: datetime,
        session: ExchangeSession | None,
        entry_window: EntryWindow | None,
        next_session: ExchangeSession,
    ) -> MarketStateSnapshot:
        valid_until = min(observed_at + self._freshness_interval, next_transition)
        return MarketStateSnapshot(
            market_state=state,
            entry_allowed=state is MarketState.ENTRY_OPEN,
            calendar=self._calendar.name,
            policy_version=self._entry_policy.version,
            observed_at=observed_at,
            valid_until=valid_until,
            next_transition=next_transition,
            session=session,
            entry_window=entry_window,
            next_session=next_session,
            calendar_timezone=self._calendar.timezone_name,
            display_timezone=self._display_timezone,
        )

    @staticmethod
    def _state_and_transition(
        observed_at: datetime,
        session: ExchangeSession,
        entry_window: EntryWindow,
        next_session: ExchangeSession,
    ) -> tuple[MarketState, datetime]:
        if observed_at < session.market_open:
            return MarketState.PRE_MARKET, session.market_open
        if observed_at < entry_window.opens_at:
            return MarketState.OPENING_BUFFER, entry_window.opens_at
        if observed_at < entry_window.closes_at:
            return MarketState.ENTRY_OPEN, entry_window.closes_at
        if observed_at < session.market_close:
            return MarketState.ENTRY_CLOSED, session.market_close
        return MarketState.POST_MARKET, next_session.market_open
