import calendar
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.audit import AuditLog
from app.models.business import Business
from app.models.subscription import (
    SubscriptionUpgradeRequest,
)
from app.services.entitlements import (
    PLAN_ADDITIONAL_MEMBER_PRICE_PHP,
    PLAN_MONTHLY_PRICE_PHP,
    EntitlementService,
)


class UpgradeRequestService:
    ACTIVE_REQUEST_STATUSES = {
        "pending",
        "awaiting_payment",
        "payment_submitted",
    }

    @staticmethod
    def quote_amount(
        plan: str,
        billing_interval: str,
        additional_member_seats: int,
    ) -> int:
        amount = PLAN_MONTHLY_PRICE_PHP[plan]
        if plan == "pro":
            amount += PLAN_ADDITIONAL_MEMBER_PRICE_PHP["pro"] * additional_member_seats
        return amount * (12 if billing_interval == "yearly" else 1)

    @classmethod
    def create_request(
        cls,
        business_id: str,
        user_id: str,
        plan: str,
        billing_interval: str,
        additional_member_seats: int,
        db: Session,
    ) -> SubscriptionUpgradeRequest:
        existing = db.execute(
            select(SubscriptionUpgradeRequest)
            .where(
                SubscriptionUpgradeRequest.business_id == business_id,
                SubscriptionUpgradeRequest.status.in_(cls.ACTIVE_REQUEST_STATUSES),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An upgrade request is already in progress for this business.",
            )

        request = SubscriptionUpgradeRequest(
            business_id=business_id,
            requested_by=user_id,
            requested_plan=plan,
            requested_billing_interval=billing_interval,
            requested_additional_member_seats=additional_member_seats,
            quoted_amount_php=cls.quote_amount(
                plan,
                billing_interval,
                additional_member_seats,
            ),
            status="pending",
        )
        db.add(request)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An upgrade request is already in progress for this business.",
            ) from exc
        return request

    @classmethod
    def mark_awaiting_payment(
        cls,
        request_id: str,
        reviewer_id: str,
        admin_note: str | None,
        db: Session,
    ) -> SubscriptionUpgradeRequest:
        request = cls._request_in_statuses(request_id, {"pending"}, db)
        request.status = "awaiting_payment"
        request.admin_note = admin_note
        request.reviewed_by = reviewer_id
        request.reviewed_at = datetime.now(timezone.utc)
        cls._write_audit_log(
            request,
            reviewer_id,
            "subscription_upgrade_request.awaiting_payment",
            db,
        )
        db.flush()
        return request

    @classmethod
    def submit_payment(
        cls,
        request_id: str,
        business_id: str,
        payment_method: str,
        payment_reference: str,
        db: Session,
    ) -> SubscriptionUpgradeRequest:
        request = cls._request_in_statuses(
            request_id,
            {"awaiting_payment"},
            db,
        )
        if str(request.business_id) != business_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upgrade request not found.",
            )
        request.status = "payment_submitted"
        request.payment_method = payment_method.strip()
        request.payment_reference = payment_reference.strip()
        request.payment_submitted_at = datetime.now(timezone.utc)
        db.flush()
        return request

    @classmethod
    def cancel_request(
        cls,
        request_id: str,
        business_id: str,
        db: Session,
    ) -> SubscriptionUpgradeRequest:
        request = cls._request_in_statuses(
            request_id,
            cls.ACTIVE_REQUEST_STATUSES,
            db,
        )
        if str(request.business_id) != business_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upgrade request not found.",
            )
        request.status = "cancelled"
        db.flush()
        return request

    @classmethod
    def approve_request(
        cls,
        request_id: str,
        reviewer_id: str,
        plan: str,
        billing_interval: str,
        additional_member_seats: int,
        payment_reference: str | None,
        admin_note: str | None,
        db: Session,
    ) -> SubscriptionUpgradeRequest:
        request = cls._request_in_statuses(request_id, {"payment_submitted"}, db)
        now = datetime.now(timezone.utc)
        amount = cls.quote_amount(plan, billing_interval, additional_member_seats)

        EntitlementService.assign_plan(
            business_id=str(request.business_id),
            plan=plan,
            status_value="active",
            provider="manual",
            current_period_started_at=now,
            current_period_ends_at=cls._period_end(now, billing_interval),
            additional_member_seats=additional_member_seats,
            billing_interval=billing_interval,
            db=db,
        )
        request.status = "approved"
        request.payment_reference = payment_reference or request.payment_reference
        request.admin_note = admin_note
        request.approved_plan = plan
        request.approved_billing_interval = billing_interval
        request.approved_additional_member_seats = additional_member_seats
        request.approved_amount_php = amount
        request.reviewed_by = reviewer_id
        request.reviewed_at = now
        cls._write_audit_log(
            request,
            reviewer_id,
            "subscription_upgrade_request.approved",
            db,
        )
        db.flush()
        return request

    @classmethod
    def reject_request(
        cls,
        request_id: str,
        reviewer_id: str,
        admin_note: str,
        db: Session,
    ) -> SubscriptionUpgradeRequest:
        request = cls._request_in_statuses(
            request_id,
            cls.ACTIVE_REQUEST_STATUSES,
            db,
        )
        request.status = "rejected"
        request.admin_note = admin_note
        request.reviewed_by = reviewer_id
        request.reviewed_at = datetime.now(timezone.utc)
        cls._write_audit_log(
            request,
            reviewer_id,
            "subscription_upgrade_request.rejected",
            db,
        )
        db.flush()
        return request

    @classmethod
    def current_request(
        cls,
        business_id: str,
        db: Session,
    ) -> SubscriptionUpgradeRequest | None:
        return db.execute(
            select(SubscriptionUpgradeRequest)
            .where(
                SubscriptionUpgradeRequest.business_id == business_id,
                SubscriptionUpgradeRequest.status.in_(cls.ACTIVE_REQUEST_STATUSES),
            )
            .order_by(SubscriptionUpgradeRequest.created_at.desc())
        ).scalar_one_or_none()

    @staticmethod
    def list_requests(
        db: Session,
        page: int,
        page_size: int,
        status_filter: str | None = None,
    ) -> tuple[list[tuple], int, dict[str, int]]:
        filters = []
        if status_filter:
            filters.append(SubscriptionUpgradeRequest.status == status_filter)

        total = db.execute(
            select(func.count(SubscriptionUpgradeRequest.id)).where(*filters)
        ).scalar_one()
        rows = db.execute(
            select(SubscriptionUpgradeRequest, Business, User)
            .join(Business, Business.id == SubscriptionUpgradeRequest.business_id)
            .outerjoin(User, User.id == SubscriptionUpgradeRequest.requested_by)
            .where(*filters)
            .order_by(
                SubscriptionUpgradeRequest.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        status_counts = {
            row._mapping["status"]: row._mapping["count"]
            for row in db.execute(
                select(
                    SubscriptionUpgradeRequest.status.label("status"),
                    func.count(SubscriptionUpgradeRequest.id).label("count"),
                ).group_by(SubscriptionUpgradeRequest.status)
            )
        }
        return rows, total, status_counts

    @staticmethod
    def serialize(
        request: SubscriptionUpgradeRequest,
        business: Business | None = None,
        user: User | None = None,
    ) -> dict:
        return {
            "id": str(request.id),
            "business_id": str(request.business_id),
            "business_name": business.name if business else None,
            "requested_by_name": (
                f"{user.first_name} {user.last_name or ''}".strip() if user else None
            ),
            "requested_by_email": user.email if user else None,
            "requested_plan": request.requested_plan,
            "requested_billing_interval": request.requested_billing_interval,
            "requested_additional_member_seats": (
                request.requested_additional_member_seats
            ),
            "quoted_amount_php": request.quoted_amount_php,
            "status": request.status,
            "payment_method": request.payment_method,
            "payment_reference": request.payment_reference,
            "payment_submitted_at": request.payment_submitted_at,
            "admin_note": request.admin_note,
            "approved_plan": request.approved_plan,
            "approved_billing_interval": request.approved_billing_interval,
            "approved_additional_member_seats": (
                request.approved_additional_member_seats
            ),
            "approved_amount_php": request.approved_amount_php,
            "reviewed_at": request.reviewed_at,
            "created_at": request.created_at,
        }

    @staticmethod
    def _request_in_statuses(
        request_id: str,
        allowed_statuses: set[str],
        db: Session,
    ) -> SubscriptionUpgradeRequest:
        request = db.execute(
            select(SubscriptionUpgradeRequest)
            .where(SubscriptionUpgradeRequest.id == request_id)
            .with_for_update()
        ).scalar_one_or_none()
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upgrade request not found.",
            )
        if request.status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This upgrade request is not available for that action.",
            )
        return request

    @staticmethod
    def _write_audit_log(
        request: SubscriptionUpgradeRequest,
        user_id: str,
        action: str,
        db: Session,
    ) -> None:
        db.add(
            AuditLog(
                business_id=request.business_id,
                user_id=user_id,
                action=action,
                entity_type="subscription_upgrade_request",
                entity_id=request.id,
                new_values={
                    "status": request.status,
                    "plan": request.approved_plan or request.requested_plan,
                    "billing_interval": (
                        request.approved_billing_interval
                        or request.requested_billing_interval
                    ),
                    "amount_php": (
                        request.approved_amount_php or request.quoted_amount_php
                    ),
                },
            )
        )

    @staticmethod
    def _period_end(now: datetime, billing_interval: str) -> datetime:
        months = 12 if billing_interval == "yearly" else 1
        month_index = now.month - 1 + months
        year = now.year + month_index // 12
        month = month_index % 12 + 1
        day = min(now.day, calendar.monthrange(year, month)[1])
        return now.replace(year=year, month=month, day=day)
