from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class SystemClock:
    def now(self) -> datetime:
        return utc_now()


@dataclass(frozen=True)
class FrozenClock:
    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensure_utc(self.value))

    def now(self) -> datetime:
        return self.value
