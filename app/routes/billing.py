from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.permissions import (
    RequestContext,
    require_permission,
)
from app.config.settings import settings
from app.core.platform_access import require_superadmin
from app.models.auth import User
from app.schemas.billing import (
    BillingAdminAccessResponse,
    SubscriptionAdminUpdate,
    SubscriptionResponse,
    UpgradeRequestApprove,
    UpgradeRequestAwaitingPayment,
    UpgradeRequestCreate,
    UpgradeRequestListResponse,
    UpgradeRequestPaymentSubmission,
    UpgradeRequestReject,
    UpgradeRequestResponse,
    UpgradeRequestStatus,
)
from app.services.entitlements import EntitlementService
from app.services.upgrade_request import UpgradeRequestService


router = APIRouter(prefix="/billing", tags=["billing"])


def require_business_owner(context: RequestContext) -> None:
    role = context.membership.role
    if not role or role.name.lower() != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the business owner can request an upgrade.",
        )


@router.get("/admin/access", response_model=BillingAdminAccessResponse)
async def get_billing_admin_access(
    _admin: User = Depends(require_superadmin),
):
    return {"authorized": True}


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


@router.get(
    "/upgrade-requests/current",
    response_model=UpgradeRequestResponse | None,
)
async def get_current_upgrade_request(
    context: RequestContext = Depends(require_permission("billing.manage")),
    db: Session = Depends(get_db),
):
    require_business_owner(context)
    request = UpgradeRequestService.current_request(str(context.business_id), db)
    return UpgradeRequestService.serialize(request) if request else None


@router.post(
    "/upgrade-requests",
    response_model=UpgradeRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_upgrade_request(
    payload: UpgradeRequestCreate,
    context: RequestContext = Depends(require_permission("billing.manage")),
    db: Session = Depends(get_db),
):
    require_business_owner(context)
    request = UpgradeRequestService.create_request(
        business_id=str(context.business_id),
        user_id=str(context.user.id),
        plan=payload.plan,
        billing_interval=payload.billing_interval,
        additional_member_seats=payload.additional_member_seats,
        db=db,
    )
    db.commit()
    db.refresh(request)
    return UpgradeRequestService.serialize(request)


@router.post(
    "/upgrade-requests/{request_id}/submit-payment",
    response_model=UpgradeRequestResponse,
)
async def submit_upgrade_request_payment(
    request_id: str,
    payload: UpgradeRequestPaymentSubmission,
    context: RequestContext = Depends(require_permission("billing.manage")),
    db: Session = Depends(get_db),
):
    require_business_owner(context)
    request = UpgradeRequestService.submit_payment(
        request_id=request_id,
        business_id=str(context.business_id),
        payment_method=payload.payment_method,
        payment_reference=payload.payment_reference,
        db=db,
    )
    db.commit()
    db.refresh(request)
    return UpgradeRequestService.serialize(request)


@router.post(
    "/upgrade-requests/{request_id}/cancel",
    response_model=UpgradeRequestResponse,
)
async def cancel_upgrade_request(
    request_id: str,
    context: RequestContext = Depends(require_permission("billing.manage")),
    db: Session = Depends(get_db),
):
    require_business_owner(context)
    request = UpgradeRequestService.cancel_request(
        request_id=request_id,
        business_id=str(context.business_id),
        db=db,
    )
    db.commit()
    db.refresh(request)
    return UpgradeRequestService.serialize(request)


@router.get(
    "/admin/upgrade-requests",
    response_model=UpgradeRequestListResponse,
)
async def list_upgrade_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    request_status: UpgradeRequestStatus
    | None = Query(
        default=None,
        alias="status",
    ),
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    rows, total, status_counts = UpgradeRequestService.list_requests(
        db,
        page,
        page_size,
        request_status,
    )
    return {
        "items": [
            UpgradeRequestService.serialize(request, business, user)
            for request, business, user in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max((total + page_size - 1) // page_size, 1),
        "status_counts": status_counts,
    }


@router.post(
    "/admin/upgrade-requests/{request_id}/awaiting-payment",
    response_model=UpgradeRequestResponse,
)
async def mark_upgrade_request_awaiting_payment(
    request_id: str,
    payload: UpgradeRequestAwaitingPayment,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    request = UpgradeRequestService.mark_awaiting_payment(
        request_id=request_id,
        reviewer_id=str(admin.id),
        admin_note=payload.admin_note,
        db=db,
    )
    db.commit()
    db.refresh(request)
    return UpgradeRequestService.serialize(request)


@router.post(
    "/admin/upgrade-requests/{request_id}/approve",
    response_model=UpgradeRequestResponse,
)
async def approve_upgrade_request(
    request_id: str,
    payload: UpgradeRequestApprove,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    request = UpgradeRequestService.approve_request(
        request_id=request_id,
        reviewer_id=str(admin.id),
        plan=payload.plan,
        billing_interval=payload.billing_interval,
        additional_member_seats=payload.additional_member_seats,
        payment_reference=payload.payment_reference,
        admin_note=payload.admin_note,
        db=db,
    )
    db.commit()
    db.refresh(request)
    return UpgradeRequestService.serialize(request)


@router.post(
    "/admin/upgrade-requests/{request_id}/reject",
    response_model=UpgradeRequestResponse,
)
async def reject_upgrade_request(
    request_id: str,
    payload: UpgradeRequestReject,
    admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    request = UpgradeRequestService.reject_request(
        request_id=request_id,
        reviewer_id=str(admin.id),
        admin_note=payload.admin_note,
        db=db,
    )
    db.commit()
    db.refresh(request)
    return UpgradeRequestService.serialize(request)


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
        billing_interval=payload.billing_interval,
        trial_ends_at=payload.trial_ends_at,
        current_period_started_at=payload.current_period_started_at,
        current_period_ends_at=payload.current_period_ends_at,
        additional_member_seats=payload.additional_member_seats,
        db=db,
    )
    db.commit()
    return EntitlementService.usage_summary(business_id, db)
