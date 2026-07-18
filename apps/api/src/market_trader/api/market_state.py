from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from market_trader.config import get_settings
from market_trader.domain.time import SystemClock
from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_calendar.models import (
    CalendarUnavailableError,
    MarketState,
    MarketStateSnapshot,
)
from market_trader.market_calendar.policy import EntryWindowPolicy
from market_trader.market_calendar.service import MarketStateService

router = APIRouter(tags=["market-state"])


class MarketStateResponse(BaseModel):
    market_state: MarketState
    entry_allowed: bool
    calendar: str
    policy_version: str
    observed_at: datetime
    valid_until: datetime
    next_transition: datetime
    session_date: date | None
    market_open: datetime | None
    market_close: datetime | None
    entry_window_open: datetime | None
    entry_window_close: datetime | None
    is_early_close: bool | None
    next_session_date: date
    next_session_open: datetime
    calendar_timezone: str
    display_timezone: str


class MarketStateUnavailableResponse(BaseModel):
    market_state: Literal["unavailable"] = "unavailable"
    entry_allowed: Literal[False] = False
    error_code: Literal["market_calendar_unavailable"] = "market_calendar_unavailable"


@lru_cache
def get_market_state_service() -> MarketStateService:
    settings = get_settings()
    clock = SystemClock()
    current_year = clock.now().year
    calendar = XNYSCalendarAdapter(
        start=date(current_year - 10, 1, 1),
        end=date(current_year + 5, 12, 31),
    )
    return MarketStateService(
        clock=clock,
        calendar=calendar,
        entry_policy=EntryWindowPolicy.v1(),
        display_timezone=settings.display_timezone,
    )


@router.get(
    "/market-state",
    response_model=MarketStateResponse,
    responses={503: {"model": MarketStateUnavailableResponse}},
)
def market_state(
    response: Response,
    service: Annotated[MarketStateService, Depends(get_market_state_service)],
) -> MarketStateResponse | JSONResponse:
    try:
        snapshot = service.current()
    except CalendarUnavailableError:
        unavailable = MarketStateUnavailableResponse()
        return JSONResponse(
            status_code=503,
            content=unavailable.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return _to_response(snapshot)


def _to_response(snapshot: MarketStateSnapshot) -> MarketStateResponse:
    session = snapshot.session
    entry_window = snapshot.entry_window
    return MarketStateResponse(
        market_state=snapshot.market_state,
        entry_allowed=snapshot.entry_allowed,
        calendar=snapshot.calendar,
        policy_version=snapshot.policy_version,
        observed_at=snapshot.observed_at,
        valid_until=snapshot.valid_until,
        next_transition=snapshot.next_transition,
        session_date=session.session_date if session else None,
        market_open=session.market_open if session else None,
        market_close=session.market_close if session else None,
        entry_window_open=entry_window.opens_at if entry_window else None,
        entry_window_close=entry_window.closes_at if entry_window else None,
        is_early_close=session.is_early_close if session else None,
        next_session_date=snapshot.next_session.session_date,
        next_session_open=snapshot.next_session.market_open,
        calendar_timezone=snapshot.calendar_timezone,
        display_timezone=snapshot.display_timezone,
    )
