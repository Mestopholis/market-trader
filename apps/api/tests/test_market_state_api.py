from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from market_trader.api.market_state import get_market_state_service
from market_trader.domain.time import FrozenClock
from market_trader.main import app
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_calendar.models import CalendarUnavailableError
from market_trader.market_calendar.policy import EntryWindowPolicy
from market_trader.market_calendar.service import MarketStateService


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def service_at(observed_at: datetime) -> MarketStateService:
    return MarketStateService(
        clock=FrozenClock(observed_at),
        calendar=XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 12, 31)),
        entry_policy=EntryWindowPolicy.v1(),
        display_timezone="America/Chicago",
    )


def test_market_state_returns_exact_read_only_contract() -> None:
    app.dependency_overrides[get_market_state_service] = lambda: service_at(
        datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
    )

    response = TestClient(app).get("/api/market-state")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "market_state": "entry_open",
        "entry_allowed": True,
        "calendar": "XNYS",
        "policy_version": "entry-window-v1",
        "observed_at": "2026-07-20T15:30:00Z",
        "valid_until": "2026-07-20T15:31:00Z",
        "next_transition": "2026-07-20T19:30:00Z",
        "session_date": "2026-07-20",
        "market_open": "2026-07-20T13:30:00Z",
        "market_close": "2026-07-20T20:00:00Z",
        "entry_window_open": "2026-07-20T13:45:00Z",
        "entry_window_close": "2026-07-20T19:30:00Z",
        "is_early_close": False,
        "next_session_date": "2026-07-21",
        "next_session_open": "2026-07-21T13:30:00Z",
        "calendar_timezone": "America/New_York",
        "display_timezone": "America/Chicago",
    }


def test_weekend_response_has_no_current_session() -> None:
    app.dependency_overrides[get_market_state_service] = lambda: service_at(
        datetime(2026, 7, 18, 15, 0, tzinfo=UTC)
    )

    body = TestClient(app).get("/api/market-state").json()

    assert body["market_state"] == "closed"
    assert body["entry_allowed"] is False
    assert body["session_date"] is None
    assert body["market_open"] is None
    assert body["entry_window_open"] is None
    assert body["next_session_date"] == "2026-07-20"


class UnavailableService:
    def current(self) -> None:
        raise CalendarUnavailableError("internal dependency detail")


def test_calendar_failure_returns_structured_fail_closed_response() -> None:
    app.dependency_overrides[get_market_state_service] = lambda: UnavailableService()

    response = TestClient(app).get("/api/market-state")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "market_state": "unavailable",
        "entry_allowed": False,
        "error_code": "market_calendar_unavailable",
    }
    assert "internal dependency detail" not in response.text


def test_calendar_failure_during_service_construction_is_structured() -> None:
    def unavailable_dependency() -> None:
        raise CalendarUnavailableError("calendar initialization detail")

    app.dependency_overrides[get_market_state_service] = unavailable_dependency

    response = TestClient(app, raise_server_exceptions=False).get("/api/market-state")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "market_state": "unavailable",
        "entry_allowed": False,
        "error_code": "market_calendar_unavailable",
    }
    assert "calendar initialization detail" not in response.text
