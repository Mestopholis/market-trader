from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_trader.catalysts.configuration import EventRiskPolicy
from market_trader.catalysts.models import (
    CatalystObservation,
    EventFamily,
    EventRiskWindow,
    RiskState,
)
from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.models import (
    CalendarUnavailableError,
    ExchangeCalendar,
    ExchangeSession,
    SessionNotFoundError,
)


class EventRiskEvaluator:
    def __init__(self, *, calendar: ExchangeCalendar, policy: EventRiskPolicy) -> None:
        self._calendar = calendar
        self._policy = policy

    def evaluate_earnings(
        self,
        symbol: str,
        observations: tuple[CatalystObservation, ...],
        *,
        as_of: datetime,
    ) -> EventRiskWindow:
        reference = ensure_utc(as_of)
        candidates = tuple(
            observation
            for observation in observations
            if observation.event_family is EventFamily.EARNINGS
            and observation.event_category == "earnings_schedule"
            and observation.symbol == symbol
        )
        current = tuple(
            observation for observation in candidates if reference <= observation.valid_until
        )
        scheduled = {
            observation.scheduled_for
            for observation in current
            if observation.scheduled_for is not None
        }
        lineage = tuple(sorted(observation.observation_key for observation in current))
        if not current or any(observation.scheduled_for is None for observation in current):
            return self._blocked(
                category="earnings",
                scope="symbol",
                symbol=symbol,
                reason="earnings_time_missing",
                lineage=lineage,
            )
        if len(scheduled) != 1:
            return self._blocked(
                category="earnings",
                scope="symbol",
                symbol=symbol,
                reason="earnings_time_conflicting",
                lineage=lineage,
            )
        scheduled_for = next(iter(scheduled))
        assert scheduled_for is not None
        try:
            event_session = self._event_session(scheduled_for)
            start_session = event_session
            for _ in range(self._policy.earnings_sessions_before):
                start_session = self._calendar.previous_session(start_session.session_date)
            post_session = self._calendar.next_session(event_session.session_date)
            while post_session.is_early_close:
                post_session = self._calendar.next_session(post_session.session_date)
        except (CalendarUnavailableError, SessionNotFoundError, ValueError):
            return self._blocked(
                category="earnings",
                scope="symbol",
                symbol=symbol,
                reason="earnings_time_missing",
                lineage=lineage,
            )
        return self._bounded(
            category="earnings",
            scope="symbol",
            symbol=symbol,
            starts_at=start_session.market_open,
            ends_at=post_session.market_close,
            active_reason="earnings_window_active",
            lineage=lineage,
            as_of=reference,
        )

    def evaluate_macro(
        self,
        category: str,
        observations: tuple[CatalystObservation, ...],
        *,
        as_of: datetime,
    ) -> EventRiskWindow:
        reference = ensure_utc(as_of)
        if category not in self._policy.high_impact_macro:
            return EventRiskWindow(
                category=category,
                scope="market",
                symbol=None,
                starts_at=None,
                ends_at=None,
                state=RiskState.CLEAR,
                reasons=(),
                lineage=(),
                policy_version=self._policy.version,
            )
        candidates = tuple(
            observation
            for observation in observations
            if observation.event_family is EventFamily.ECONOMIC_RELEASE
            and observation.event_category == category
            and reference <= observation.valid_until
        )
        scheduled = {
            observation.scheduled_for
            for observation in candidates
            if observation.scheduled_for is not None
        }
        lineage = tuple(sorted(observation.observation_key for observation in candidates))
        if not candidates or any(
            observation.scheduled_for is None for observation in candidates
        ):
            return self._blocked(
                category=category,
                scope="market",
                symbol=None,
                reason="macro_schedule_missing",
                lineage=lineage,
            )
        if len(scheduled) != 1:
            return self._blocked(
                category=category,
                scope="market",
                symbol=None,
                reason="macro_schedule_conflicting",
                lineage=lineage,
            )
        scheduled_for = next(iter(scheduled))
        assert scheduled_for is not None
        return self._bounded(
            category=category,
            scope="market",
            symbol=None,
            starts_at=scheduled_for
            - timedelta(minutes=self._policy.macro_minutes_before),
            ends_at=scheduled_for + timedelta(minutes=self._policy.macro_minutes_after),
            active_reason="macro_window_active",
            lineage=lineage,
            as_of=reference,
        )

    def _event_session(self, scheduled_for: datetime) -> ExchangeSession:
        scheduled = ensure_utc(scheduled_for)
        session_date = scheduled.astimezone(ZoneInfo(self._calendar.timezone_name)).date()
        if self._calendar.is_session(session_date):
            return self._calendar.session(session_date)
        return self._calendar.next_session(session_date)

    def _bounded(
        self,
        *,
        category: str,
        scope: str,
        symbol: str | None,
        starts_at: datetime,
        ends_at: datetime,
        active_reason: str,
        lineage: tuple[str, ...],
        as_of: datetime,
    ) -> EventRiskWindow:
        active = starts_at <= as_of <= ends_at
        return EventRiskWindow(
            category=category,
            scope=scope,
            symbol=symbol,
            starts_at=starts_at,
            ends_at=ends_at,
            state=RiskState.ACTIVE if active else RiskState.CLEAR,
            reasons=(active_reason,) if active else (),
            lineage=lineage,
            policy_version=self._policy.version,
        )

    def _blocked(
        self,
        *,
        category: str,
        scope: str,
        symbol: str | None,
        reason: str,
        lineage: tuple[str, ...],
    ) -> EventRiskWindow:
        return EventRiskWindow(
            category=category,
            scope=scope,
            symbol=symbol,
            starts_at=None,
            ends_at=None,
            state=RiskState.BLOCKED,
            reasons=(reason,),
            lineage=lineage,
            policy_version=self._policy.version,
        )


def display_risk_bounds(
    window: EventRiskWindow,
    timezone_name: str,
) -> tuple[datetime | None, datetime | None]:
    timezone = ZoneInfo(timezone_name)
    starts_at = None if window.starts_at is None else window.starts_at.astimezone(timezone)
    ends_at = None if window.ends_at is None else window.ends_at.astimezone(timezone)
    return starts_at, ends_at
