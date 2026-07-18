from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from market_trader.market_data.rate_limit import (
    InMemoryRateLimitBoundary,
    RateLimitState,
)

NOW = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)


def test_throttle_boundary_is_deterministic_and_inclusive() -> None:
    clock = MutableClock(NOW)
    boundary = InMemoryRateLimitBoundary(clock=clock)
    retry_at = NOW + timedelta(seconds=30)
    boundary.throttle("fixture", retry_at=retry_at)

    assert boundary.check("fixture").state is RateLimitState.THROTTLED
    clock.advance_to(retry_at)

    status = boundary.check("fixture")
    assert status.state is RateLimitState.ALLOWED
    assert status.transitioned_at == retry_at
    assert status.retry_at is None


def test_unavailable_and_recovering_states_are_explicit() -> None:
    clock = MutableClock(NOW)
    boundary = InMemoryRateLimitBoundary(clock=clock)

    unavailable = boundary.mark_unavailable("fixture", reason_code="provider_unavailable")
    assert unavailable.state is RateLimitState.UNAVAILABLE
    assert unavailable.reason_code == "provider_unavailable"

    clock.advance_to(NOW + timedelta(seconds=5))
    recovering = boundary.mark_recovering("fixture", reason_code="provider_recovering")
    assert recovering.state is RateLimitState.RECOVERING
    assert recovering.transitioned_at == clock.now()

    allowed = boundary.allow("fixture")
    assert allowed.state is RateLimitState.ALLOWED
    assert allowed.reason_code is None


def test_unknown_source_defaults_to_allowed() -> None:
    boundary = InMemoryRateLimitBoundary(clock=MutableClock(NOW))

    status = boundary.check("new-source")

    assert status.state is RateLimitState.ALLOWED
    assert status.source == "new-source"


@dataclass
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value

    def advance_to(self, value: datetime) -> None:
        if value < self.value:
            raise ValueError("clock cannot move backward")
        self.value = value
