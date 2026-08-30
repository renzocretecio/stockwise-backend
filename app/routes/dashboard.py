from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import RequestContext, require_permission
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import DashboardService


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return DashboardService.get_dashboard(str(context.business_id), db)
