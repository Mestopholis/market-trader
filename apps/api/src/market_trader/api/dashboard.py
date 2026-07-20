from typing import Annotated

from fastapi import APIRouter, Depends, Response

from market_trader.dashboard.models import DashboardOverview
from market_trader.dashboard.read_models import DashboardReadModel

router = APIRouter(tags=["dashboard"])


def get_dashboard_read_model() -> DashboardReadModel:
    return DashboardReadModel()


@router.get("/overview", response_model=DashboardOverview)
def dashboard_overview(
    response: Response,
    read_model: Annotated[DashboardReadModel, Depends(get_dashboard_read_model)],
) -> DashboardOverview:
    response.headers["Cache-Control"] = "no-store"
    return read_model.overview()
