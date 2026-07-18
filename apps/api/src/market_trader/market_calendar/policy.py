from dataclasses import dataclass
from datetime import datetime, timedelta

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.models import EntryWindow, ExchangeSession


@dataclass(frozen=True)
class EntryWindowPolicy:
    opening_delay: timedelta
    closing_buffer: timedelta
    version: str

    @classmethod
    def v1(cls) -> "EntryWindowPolicy":
        return cls(
            opening_delay=timedelta(minutes=15),
            closing_buffer=timedelta(minutes=30),
            version="entry-window-v1",
        )

    def window_for(self, session: ExchangeSession) -> EntryWindow:
        opens_at = session.market_open + self.opening_delay
        closes_at = session.market_close - self.closing_buffer
        if opens_at >= closes_at:
            raise ValueError("entry window must have positive duration")
        return EntryWindow(
            opens_at=opens_at,
            closes_at=closes_at,
            policy_version=self.version,
        )

    def allows(self, value: datetime, window: EntryWindow) -> bool:
        observed_at = ensure_utc(value)
        return window.opens_at <= observed_at < window.closes_at
