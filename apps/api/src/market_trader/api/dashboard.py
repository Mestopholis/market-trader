from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from market_trader.api.auth import require_authenticated_session
from market_trader.dashboard.models import (
    AnalyticsSummary,
    CandidateDetail,
    CandidateListResponse,
    DashboardOverview,
    JournalEventListResponse,
    RiskSummary,
)
from market_trader.dashboard.read_models import DashboardReadModel

router = APIRouter(tags=["dashboard"], dependencies=[Depends(require_authenticated_session)])

Cursor = Annotated[str | None, Query(pattern=r"^[A-Za-z0-9:_-]+$")]
EventFilter = Annotated[str | None, Query(pattern=r"^[A-Za-z0-9:_.-]+$")]
Limit = Annotated[int, Query(ge=1, le=100)]


def get_dashboard_read_model() -> DashboardReadModel:
    return DashboardReadModel()


@router.get("/overview", response_model=DashboardOverview)
def dashboard_overview(
    response: Response,
    read_model: Annotated[DashboardReadModel, Depends(get_dashboard_read_model)],
) -> DashboardOverview:
    response.headers["Cache-Control"] = "no-store"
    return read_model.overview()


@router.get("/candidates", response_model=CandidateListResponse)
def dashboard_candidates(
    response: Response,
    read_model: Annotated[DashboardReadModel, Depends(get_dashboard_read_model)],
    limit: Limit = 50,
    cursor: Cursor = None,
) -> CandidateListResponse:
    response.headers["Cache-Control"] = "no-store"
    return read_model.candidates(limit=limit, cursor=cursor)


@router.get("/candidates/{candidate_key}", response_model=CandidateDetail)
def dashboard_candidate_detail(
    candidate_key: str,
    response: Response,
    read_model: Annotated[DashboardReadModel, Depends(get_dashboard_read_model)],
) -> CandidateDetail:
    response.headers["Cache-Control"] = "no-store"
    detail = read_model.candidate_detail(candidate_key)
    if detail is None:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    return detail


@router.get("/risk", response_model=RiskSummary)
def dashboard_risk(
    response: Response,
    read_model: Annotated[DashboardReadModel, Depends(get_dashboard_read_model)],
) -> RiskSummary:
    response.headers["Cache-Control"] = "no-store"
    return read_model.risk()


@router.get("/journal", response_model=JournalEventListResponse)
def dashboard_journal(
    response: Response,
    read_model: Annotated[DashboardReadModel, Depends(get_dashboard_read_model)],
    limit: Limit = 50,
    cursor: Cursor = None,
    event_type: EventFilter = None,
    correlation_id: Cursor = None,
) -> JournalEventListResponse:
    response.headers["Cache-Control"] = "no-store"
    return read_model.journal(
        limit=limit,
        cursor=cursor,
        event_type=event_type,
        correlation_id=correlation_id,
    )


@router.get("/analytics", response_model=AnalyticsSummary)
def dashboard_analytics(
    response: Response,
    read_model: Annotated[DashboardReadModel, Depends(get_dashboard_read_model)],
) -> AnalyticsSummary:
    response.headers["Cache-Control"] = "no-store"
    return read_model.analytics()
