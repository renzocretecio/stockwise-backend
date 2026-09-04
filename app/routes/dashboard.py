from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import RequestContext, require_permission
from app.schemas.dashboard import DashboardResponse, DashboardTrendsResponse
from app.services.dashboard import DashboardService
from app.services.dashboard_trends import DashboardTrendsService


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    stock_days_threshold: int = Query(default=7, ge=1, le=90),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return DashboardService.get_dashboard(
        str(context.business_id),
        db,
        stock_days_threshold,
    )


@router.get("/trends", response_model=DashboardTrendsResponse)
async def get_dashboard_trends(
    start_date: date = Query(),
    end_date: date = Query(),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date.",
        )
    if (end_date - start_date).days + 1 > 365:
        raise HTTPException(
            status_code=422,
            detail="The date range cannot exceed 365 days.",
        )

    return DashboardTrendsService.get_trends(
        business_id=str(context.business_id),
        db=db,
        start_date=start_date,
        end_date=end_date,
        timezone_name=context.membership.business.timezone,
    )
