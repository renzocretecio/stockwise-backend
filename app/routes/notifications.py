from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import RequestContext, require_permission
from app.config.settings import settings
from app.models.notification import WeeklyOwnerSummarySettings
from app.schemas.notification import (
    WeeklyOwnerSummaryResponse,
    WeeklyOwnerSummarySettingsPayload,
    WeeklyOwnerSummarySettingsResponse,
)
from app.services.weekly_owner_summary import WeeklyOwnerSummaryService


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _owner_only(context: RequestContext):
    if not context.membership.role or context.membership.role.name.lower() != "owner":
        raise HTTPException(status_code=403, detail="Only the business owner can update notification settings")


@router.get("/weekly-owner-summary", response_model=WeeklyOwnerSummarySettingsResponse)
async def get_weekly_owner_summary_settings(
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    business = context.membership.business
    row = WeeklyOwnerSummaryService.get_or_create_settings(
        business, context.user.email, db
    )
    return {**row.__dict__, "business_id": str(row.business_id)}


@router.put("/weekly-owner-summary", response_model=WeeklyOwnerSummarySettingsResponse)
async def update_weekly_owner_summary_settings(
    payload: WeeklyOwnerSummarySettingsPayload,
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    _owner_only(context)
    business = context.membership.business
    row = WeeklyOwnerSummaryService.get_or_create_settings(
        business, context.user.email, db
    )
    row.enabled = payload.enabled
    row.send_weekday = int(payload.send_weekday)
    row.send_hour = payload.send_hour
    row.send_minute = payload.send_minute
    row.recipients = payload.recipients
    row.included_sections = payload.included_sections
    row.action_required_only = payload.action_required_only
    db.add(row)
    db.commit()
    db.refresh(row)
    return {**row.__dict__, "business_id": str(row.business_id)}


@router.get("/weekly-owner-summary/preview", response_model=WeeklyOwnerSummaryResponse)
async def preview_weekly_owner_summary(
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    business = context.membership.business
    row = WeeklyOwnerSummaryService.get_or_create_settings(
        business, context.user.email, db
    )
    data = await WeeklyOwnerSummaryService.preview(business, row, db)
    return {**data, "open_stockwise_url": settings.APP_URL}


@router.post("/weekly-owner-summary/send", response_model=WeeklyOwnerSummaryResponse)
async def send_weekly_owner_summary(
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    _owner_only(context)
    business = context.membership.business
    row = WeeklyOwnerSummaryService.get_or_create_settings(
        business, context.user.email, db
    )
    data = await WeeklyOwnerSummaryService.send_now(business, row, db)
    return {**data, "open_stockwise_url": settings.APP_URL}