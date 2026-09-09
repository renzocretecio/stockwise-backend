from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.permissions import (
    RequestContext,
    require_permission,
)
from app.config.settings import settings
from app.schemas.billing import SubscriptionAdminUpdate, SubscriptionResponse
from app.services.entitlements import EntitlementService


router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_current_subscription(
    context: RequestContext = Depends(require_permission("billing.read")),
    db: Session = Depends(get_db),
):
    return EntitlementService.usage_summary(
        str(context.business_id),
        db,
        user_id=str(context.user.id),
    )


@router.post("/subscription/trial", response_model=SubscriptionResponse)
async def start_pro_trial(
    context: RequestContext = Depends(require_permission("billing.manage")),
    db: Session = Depends(get_db),
):
    business_id = str(context.business_id)
    EntitlementService.start_pro_trial(
        business_id,
        str(context.user.id),
        db,
    )
    db.commit()
    return EntitlementService.usage_summary(
        business_id,
        db,
        user_id=str(context.user.id),
    )


@router.put(
    "/internal/businesses/{business_id}/subscription",
    response_model=SubscriptionResponse,
)
async def assign_subscription(
    business_id: str,
    payload: SubscriptionAdminUpdate,
    x_billing_admin_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected_token = settings.BILLING_ADMIN_TOKEN
    if (
        not expected_token
        or not x_billing_admin_token
        or not compare_digest(
            expected_token,
            x_billing_admin_token,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Billing administration is not authorized.",
        )

    EntitlementService.assign_plan(
        business_id=business_id,
        plan=payload.plan,
        status_value=payload.status,
        provider=payload.provider,
        trial_ends_at=payload.trial_ends_at,
        current_period_ends_at=payload.current_period_ends_at,
        additional_member_seats=payload.additional_member_seats,
        db=db,
    )
    db.commit()
    return EntitlementService.usage_summary(business_id, db)
