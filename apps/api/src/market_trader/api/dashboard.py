from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from market_trader.dashboard.models import CandidateDetail, CandidateListResponse, DashboardOverview
from market_trader.dashboard.read_models import DashboardReadModel

router = APIRouter(tags=["dashboard"])

Cursor = Annotated[str | None, Query(pattern=r"^[A-Za-z0-9:_-]+$")]
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
