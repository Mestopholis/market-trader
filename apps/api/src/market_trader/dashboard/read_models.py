from __future__ import annotations

from market_trader.api.health import database_state
from market_trader.config import get_settings
from market_trader.dashboard.models import (
    CandidateDetail,
    CandidateListResponse,
    DashboardOverview,
    DataState,
    SourceSummary,
    WarningSummary,
)
from market_trader.domain.time import SystemClock
from market_trader.market_calendar.models import CalendarUnavailableError
from market_trader.market_calendar.service import MarketStateService


class DashboardReadModel:
    def __init__(self, market_state_service: MarketStateService | None = None) -> None:
        self._clock = SystemClock()
        self._market_state_service = market_state_service

    def overview(self) -> DashboardOverview:
        settings = get_settings()
        as_of = self._clock.now()
        market_state = "unavailable"
        entry_allowed = False
        sources: list[SourceSummary] = [
            SourceSummary(
                name="database",
                state=_database_data_state(settings.database_url),
                version="storage-v1",
                observed_at=as_of,
                stable_key="database:health",
            ),
            SourceSummary(
                name="scanner",
                state=DataState.UNAVAILABLE,
                version="scanner-policy-v1",
                observed_at=as_of,
                stable_key="scanner:latest",
            ),
            SourceSummary(
                name="catalysts",
                state=DataState.UNAVAILABLE,
                version="catalyst-policy-v1",
                observed_at=as_of,
                stable_key="catalysts:latest",
            ),
            SourceSummary(
                name="options",
                state=DataState.UNAVAILABLE,
                version="options-analysis-policy-v1",
                observed_at=as_of,
                stable_key="options:latest",
            ),
            SourceSummary(
                name="risk",
                state=DataState.UNAVAILABLE,
                version="risk-policy-v1",
                observed_at=as_of,
                stable_key="risk:latest",
            ),
        ]
        warnings: list[WarningSummary] = []

        try:
            snapshot = self._market_state().current()
        except CalendarUnavailableError:
            sources.append(
                SourceSummary(
                    name="market_state",
                    state=DataState.UNAVAILABLE,
                    version="entry-window-v1",
                    observed_at=as_of,
                    stable_key="market-state:current",
                )
            )
            warnings.append(
                WarningSummary(
                    code="market_state.unavailable",
                    severity="warning",
                    message="Market schedule is unavailable",
                    source_keys=("market-state:current",),
                )
            )
            data_state = DataState.UNAVAILABLE
        else:
            as_of = snapshot.observed_at
            market_state = snapshot.market_state.value
            entry_allowed = snapshot.entry_allowed
            sources.append(
                SourceSummary(
                    name="market_state",
                    state=DataState.READY,
                    version=snapshot.policy_version,
                    observed_at=snapshot.observed_at,
                    stable_key=f"market-state:{snapshot.calendar}",
                )
            )
            data_state = DataState.PARTIAL

        return DashboardOverview(
            as_of=as_of,
            data_state=data_state,
            paper_mode=True,
            market_state=market_state,
            entry_allowed=entry_allowed,
            sources=tuple(sources),
            warnings=tuple(warnings),
        )

    def candidates(self, *, limit: int, cursor: str | None) -> CandidateListResponse:
        as_of = self._clock.now()
        return CandidateListResponse(
            as_of=as_of,
            data_state=DataState.UNAVAILABLE,
            candidates=(),
            next_cursor=None,
            sources=(
                SourceSummary(
                    name="scanner",
                    state=DataState.UNAVAILABLE,
                    version="scanner-policy-v1",
                    observed_at=as_of,
                    stable_key="scanner:latest",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="candidates.unavailable",
                    severity="warning",
                    message="Candidate records are unavailable",
                    source_keys=("scanner:latest",),
                ),
            ),
        )

    def candidate_detail(self, candidate_key: str) -> CandidateDetail | None:
        return None

    def _market_state(self) -> MarketStateService:
        if self._market_state_service is not None:
            return self._market_state_service

        from market_trader.api.market_state import get_market_state_service

        return get_market_state_service()


def _database_data_state(database_url: str) -> DataState:
    if database_state(database_url) == "ok":
        return DataState.READY
    return DataState.UNAVAILABLE
