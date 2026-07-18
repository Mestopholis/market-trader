from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from market_trader.domain.time import Clock, ensure_utc


class RateLimitState(StrEnum):
    ALLOWED = "allowed"
    THROTTLED = "throttled"
    UNAVAILABLE = "unavailable"
    RECOVERING = "recovering"


@dataclass(frozen=True)
class RateLimitStatus:
    source: str
    state: RateLimitState
    transitioned_at: datetime
    retry_at: datetime | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "transitioned_at", ensure_utc(self.transitioned_at))
        if self.retry_at is not None:
            object.__setattr__(self, "retry_at", ensure_utc(self.retry_at))


class RateLimitBoundary(Protocol):
    def check(self, source: str) -> RateLimitStatus: ...


class InMemoryRateLimitBoundary:
    def __init__(self, *, clock: Clock) -> None:
        self._clock = clock
        self._states: dict[str, RateLimitStatus] = {}

    def check(self, source: str) -> RateLimitStatus:
        status = self._states.get(source)
        if status is None:
            return self._status(source, RateLimitState.ALLOWED)
        if (
            status.state is RateLimitState.THROTTLED
            and status.retry_at is not None
            and self._clock.now() >= status.retry_at
        ):
            return self.allow(source)
        return status

    def throttle(self, source: str, *, retry_at: datetime) -> RateLimitStatus:
        status = self._status(
            source,
            RateLimitState.THROTTLED,
            retry_at=ensure_utc(retry_at),
            reason_code="provider_throttled",
        )
        self._states[source] = status
        return status

    def mark_unavailable(self, source: str, *, reason_code: str) -> RateLimitStatus:
        status = self._status(
            source,
            RateLimitState.UNAVAILABLE,
            reason_code=reason_code,
        )
        self._states[source] = status
        return status

    def mark_recovering(self, source: str, *, reason_code: str) -> RateLimitStatus:
        status = self._status(
            source,
            RateLimitState.RECOVERING,
            reason_code=reason_code,
        )
        self._states[source] = status
        return status

    def allow(self, source: str) -> RateLimitStatus:
        status = self._status(source, RateLimitState.ALLOWED)
        self._states[source] = status
        return status

    def _status(
        self,
        source: str,
        state: RateLimitState,
        *,
        retry_at: datetime | None = None,
        reason_code: str | None = None,
    ) -> RateLimitStatus:
        return RateLimitStatus(
            source=source,
            state=state,
            transitioned_at=self._clock.now(),
            retry_at=retry_at,
            reason_code=reason_code,
        )
