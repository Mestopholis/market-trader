from dataclasses import dataclass
from datetime import date, datetime, timedelta

from market_trader.domain.time import Clock, ensure_utc
from market_trader.market_calendar.models import ExchangeCalendar
from market_trader.market_data.models import DataKind, QualityState

FUTURE_TOLERANCE_V1 = timedelta(seconds=5)


@dataclass(frozen=True)
class FreshnessAssessment:
    state: QualityState
    valid_until: datetime
    reason_codes: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "valid_until", ensure_utc(self.valid_until))
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))

    @property
    def blocking(self) -> bool:
        return self.state in (QualityState.STALE, QualityState.QUARANTINED)


@dataclass(frozen=True)
class FreshnessPolicy:
    calendar: ExchangeCalendar
    clock: Clock
    version: str
    quote_max_age: timedelta
    one_minute_candle_grace: timedelta
    option_chain_max_age: timedelta
    corporate_action_max_age: timedelta
    daily_candle_grace: timedelta
    future_tolerance: timedelta

    @classmethod
    def v1(cls, *, calendar: ExchangeCalendar, clock: Clock) -> "FreshnessPolicy":
        return cls(
            calendar=calendar,
            clock=clock,
            version="market-data-freshness-v1",
            quote_max_age=timedelta(seconds=15),
            one_minute_candle_grace=timedelta(seconds=90),
            option_chain_max_age=timedelta(seconds=60),
            corporate_action_max_age=timedelta(hours=24),
            daily_candle_grace=timedelta(seconds=90),
            future_tolerance=FUTURE_TOLERANCE_V1,
        )

    def evaluate(
        self,
        data_kind: DataKind,
        *,
        observed_at: datetime,
        ingested_at: datetime,
        candle_end: datetime | None = None,
    ) -> FreshnessAssessment:
        observed_at = ensure_utc(observed_at)
        ingested_at = ensure_utc(ingested_at)
        if observed_at > ingested_at + self.future_tolerance:
            return self._assessment(
                QualityState.QUARANTINED,
                ingested_at + self.future_tolerance,
                ("future_timestamp",),
            )

        if data_kind is DataKind.QUOTE:
            valid_until = observed_at + self.quote_max_age
        elif data_kind is DataKind.CANDLE:
            if candle_end is None:
                raise ValueError("one-minute candle freshness requires candle_end")
            candle_end = ensure_utc(candle_end)
            if candle_end > ingested_at + self.future_tolerance:
                return self._assessment(
                    QualityState.QUARANTINED,
                    ingested_at + self.future_tolerance,
                    ("future_timestamp",),
                )
            valid_until = candle_end + self.one_minute_candle_grace
        elif data_kind is DataKind.OPTION_CHAIN:
            valid_until = observed_at + self.option_chain_max_age
        elif data_kind is DataKind.CORPORATE_ACTION:
            valid_until = ingested_at + self.corporate_action_max_age
        else:
            raise ValueError(f"freshness is not defined for {data_kind.value}")

        state = QualityState.STALE if self.clock.now() > valid_until else QualityState.VALID
        reasons = ("stale",) if state is QualityState.STALE else ()
        return self._assessment(state, valid_until, reasons)

    def evaluate_daily_candle(self, *, session_date: date) -> FreshnessAssessment:
        next_session = self.calendar.next_session(session_date)
        valid_until = next_session.market_close + self.daily_candle_grace
        state = QualityState.STALE if self.clock.now() > valid_until else QualityState.VALID
        reasons = ("stale",) if state is QualityState.STALE else ()
        return self._assessment(state, valid_until, reasons)

    def _assessment(
        self,
        state: QualityState,
        valid_until: datetime,
        reasons: tuple[str, ...],
    ) -> FreshnessAssessment:
        return FreshnessAssessment(
            state=state,
            valid_until=valid_until,
            reason_codes=reasons,
            policy_version=self.version,
        )
