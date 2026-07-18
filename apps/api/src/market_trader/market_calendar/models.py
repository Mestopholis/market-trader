from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from market_trader.domain.time import ensure_utc


class CalendarUnavailableError(RuntimeError):
    pass


class SessionNotFoundError(LookupError):
    pass


class MarketState(StrEnum):
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    OPENING_BUFFER = "opening_buffer"
    ENTRY_OPEN = "entry_open"
    ENTRY_CLOSED = "entry_closed"
    POST_MARKET = "post_market"


@dataclass(frozen=True)
class ExchangeSession:
    calendar: str
    session_date: date
    market_open: datetime
    market_close: datetime
    is_early_close: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "market_open", ensure_utc(self.market_open))
        object.__setattr__(self, "market_close", ensure_utc(self.market_close))
        if self.market_close <= self.market_open:
            raise ValueError("session close must be after session open")


@dataclass(frozen=True)
class EntryWindow:
    opens_at: datetime
    closes_at: datetime
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "opens_at", ensure_utc(self.opens_at))
        object.__setattr__(self, "closes_at", ensure_utc(self.closes_at))
        if self.opens_at >= self.closes_at:
            raise ValueError("entry window must have positive duration")


class ExchangeCalendar(Protocol):
    name: str
    timezone_name: str

    def is_session(self, session_date: date) -> bool: ...

    def session(self, session_date: date) -> ExchangeSession: ...

    def next_session(self, after: date) -> ExchangeSession: ...

    def previous_session(self, before: date) -> ExchangeSession: ...

    def sessions_between(self, start: date, end: date) -> tuple[ExchangeSession, ...]: ...

    def session_for_timestamp(self, value: datetime) -> ExchangeSession | None: ...
