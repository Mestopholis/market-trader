from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from market_trader.domain.time import ensure_utc


class JobKind(StrEnum):
    SCAN = "scan"
    REFRESH = "refresh"
    END_OF_DAY = "end_of_day"
    RECOVERY = "recovery"


class SessionWindow(StrEnum):
    REGULAR = "regular"
    ENTRY = "entry"


class SessionAnchor(StrEnum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class RecurringSchedule:
    schedule_id: str
    job_kind: JobKind
    window: SessionWindow
    interval: timedelta
    policy_version: str

    def __post_init__(self) -> None:
        if self.interval <= timedelta(0):
            raise ValueError("recurring interval must be positive")
        if not self.schedule_id or not self.policy_version:
            raise ValueError("schedule identity and policy version are required")


@dataclass(frozen=True)
class SessionOffsetSchedule:
    schedule_id: str
    job_kind: JobKind
    anchor: SessionAnchor
    offset: timedelta
    policy_version: str

    def __post_init__(self) -> None:
        if not self.schedule_id or not self.policy_version:
            raise ValueError("schedule identity and policy version are required")


ScheduleDefinition = RecurringSchedule | SessionOffsetSchedule


@dataclass(frozen=True)
class ScheduledRun:
    schedule_id: str
    job_kind: JobKind
    session_date: date
    scheduled_for: datetime
    calendar: str
    policy_version: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "scheduled_for", ensure_utc(self.scheduled_for))
