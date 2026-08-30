from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.config.database import get_db
from app.config.permissions import RequestContext, require_permission
from app.models.briefing import InventoryRecommendation
from app.schemas.briefing import BriefingEnvelope, RecommendationActionResponse
from app.services.briefing import BriefingService


router = APIRouter(prefix="/briefings", tags=["briefings"])


@router.get("/today", response_model=BriefingEnvelope)
async def get_today_briefing(
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    business_id = str(context.business_id)
    briefing = BriefingService.get_today(business_id, db)
    if briefing is None:
        briefing = await BriefingService.generate(
            business_id=business_id,
            user_id=str(context.user.id),
            db=db,
        )
    return {"success": True, "briefing": briefing}


@router.post("/generate", response_model=BriefingEnvelope)
async def generate_briefing(
    force: bool = Query(default=False),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    briefing = await BriefingService.generate(
        business_id=str(context.business_id),
        user_id=str(context.user.id),
        db=db,
        force=force,
    )
    return {"success": True, "briefing": briefing}


def _update_recommendation(recommendation_id: str, business_id: str, db: Session, field: str) -> dict:
    recommendation = db.execute(
        select(InventoryRecommendation)
        .join(InventoryRecommendation.briefing)
        .where(InventoryRecommendation.id == recommendation_id)
    ).scalar_one_or_none()
    if not recommendation or str(recommendation.briefing.business_id) != business_id:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    setattr(recommendation, field, datetime.now(timezone.utc))
    db.add(recommendation); db.commit()
    return {"success": True, "recommendation_id": str(recommendation.id), "status": field.removesuffix("_at")}


@router.post("/recommendations/{recommendation_id}/dismiss", response_model=RecommendationActionResponse)
async def dismiss_recommendation(recommendation_id: str, context: RequestContext = Depends(require_permission("reports.read")), db: Session = Depends(get_db)):
    return _update_recommendation(recommendation_id, str(context.business_id), db, "dismissed_at")


@router.post("/recommendations/{recommendation_id}/resolve", response_model=RecommendationActionResponse)
async def resolve_recommendation(recommendation_id: str, context: RequestContext = Depends(require_permission("reports.read")), db: Session = Depends(get_db)):
    return _update_recommendation(recommendation_id, str(context.business_id), db, "resolved_at")
