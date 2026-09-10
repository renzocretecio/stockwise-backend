from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.auth import User
from app.models.membership import BusinessMembership
from app.models.invitation import BusinessInvitation
from app.models.product import Product
from app.models.subscription import BusinessSubscription, SubscriptionUsage


PlanName = Literal["free", "pro", "business"]


@dataclass(frozen=True)
class PlanEntitlements:
    active_sku_limit: int | None
    member_limit: int | None
    ai_insights_weekly: int | None
    offline_sync: bool
    ai_insights: bool
    forecasting: bool
    reorder_assistant: bool
    weekly_owner_summary: bool
    custom_roles: bool


FREE_ENTITLEMENTS = PlanEntitlements(
    active_sku_limit=50,
    member_limit=1,
    ai_insights_weekly=5,
    offline_sync=False,
    ai_insights=True,
    forecasting=True,
    reorder_assistant=True,
    weekly_owner_summary=False,
    custom_roles=False,
)

# Paid plans inherit the complete lower-tier capability set. They only
# override capacity limits and paid operational features.
PRO_ENTITLEMENTS = replace(
    FREE_ENTITLEMENTS,
    active_sku_limit=500,
    member_limit=3,
    ai_insights_weekly=30,
    offline_sync=True,
    weekly_owner_summary=True,
)
BUSINESS_ENTITLEMENTS = replace(
    PRO_ENTITLEMENTS,
    active_sku_limit=10_000,
    member_limit=25,
    ai_insights_weekly=150,
    custom_roles=True,
)

PLAN_ENTITLEMENTS: dict[str, PlanEntitlements] = {
    "free": FREE_ENTITLEMENTS,
    "pro": PRO_ENTITLEMENTS,
    "business": BUSINESS_ENTITLEMENTS,
}

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
# Keep the stored metric name for compatibility with usage already recorded
# before the customer-facing terminology changed to "AI insights".
AI_INSIGHT_METRIC = "ai_requests_weekly"
PLAN_MONTHLY_PRICE_PHP = {
    "free": 0,
    "pro": 299,
    "business": 899,
}
PLAN_MAX_MEMBER_LIMIT = {
    "free": 1,
    "pro": 10,
    "business": 25,
}
PLAN_ADDITIONAL_MEMBER_PRICE_PHP = {
    "free": None,
    "pro": 79,
    "business": None,
}
PRO_TRIAL_DAYS = 14


class EntitlementService:
    @classmethod
    def require_membership_access(
        cls,
        membership: BusinessMembership,
        db: Session,
    ) -> None:
        """Keep the owner available while enforcing downgrade overages."""
        role = membership.role
        if role and role.name.lower() == "owner":
            return

        plan, entitlements, subscription = cls.entitlements_for_business(
            str(membership.business_id),
            db,
        )
        if role and not role.is_system_role and not entitlements.custom_roles:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "custom_role_plan_required",
                    "current_plan": plan,
                    "message": (
                        "An owner must assign you a built-in role before "
                        "you can access this business on its current plan."
                    ),
                },
            )

        limit = cls.effective_member_limit(
            plan,
            entitlements,
            subscription,
        )
        if limit is None:
            return
        active_members = db.execute(
            select(func.count(BusinessMembership.id)).where(
                BusinessMembership.business_id == membership.business_id,
                BusinessMembership.status == "active",
            )
        ).scalar_one()
        if active_members > limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "member_limit_exceeded",
                    "current_plan": plan,
                    "limit": limit,
                    "message": (
                        "The business is over its member limit. Ask the "
                        "owner to update the plan or remove extra members."
                    ),
                },
            )

    @staticmethod
    def user_has_used_pro_trial(user_id: str, db: Session) -> bool:
        used_at = db.execute(
            select(User.pro_trial_used_at).where(User.id == user_id)
        ).scalar_one_or_none()
        return used_at is not None

    @staticmethod
    def ai_period_start(business_id: str, db: Session) -> date:
        timezone_name = (
            db.execute(
                select(Business.timezone).where(Business.id == business_id)
            ).scalar_one_or_none()
            or "UTC"
        )
        try:
            business_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            business_timezone = ZoneInfo("UTC")
        today = datetime.now(business_timezone).date()
        return today - timedelta(days=today.weekday())

    @staticmethod
    def subscription_for_business(
        business_id: str,
        db: Session,
    ) -> BusinessSubscription | None:
        return db.execute(
            select(BusinessSubscription).where(
                BusinessSubscription.business_id == business_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def effective_plan(subscription: BusinessSubscription | None) -> PlanName:
        if subscription and subscription.status == "trialing":
            trial_ends_at = subscription.trial_ends_at
            if not trial_ends_at:
                return "free"
            if trial_ends_at.tzinfo is None:
                trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
            if trial_ends_at <= datetime.now(timezone.utc):
                return "free"
        if (
            subscription
            and subscription.plan in PLAN_ENTITLEMENTS
            and subscription.status in ACTIVE_SUBSCRIPTION_STATUSES
        ):
            period_ends_at = subscription.current_period_ends_at
            if (
                subscription.status == "active"
                and period_ends_at is not None
                and (
                    period_ends_at.replace(tzinfo=timezone.utc)
                    if period_ends_at.tzinfo is None
                    else period_ends_at
                )
                <= datetime.now(timezone.utc)
            ):
                return "free"
            return subscription.plan  # type: ignore[return-value]
        return "free"

    @classmethod
    def effective_member_limit(
        cls,
        plan: PlanName,
        entitlements: PlanEntitlements,
        subscription: BusinessSubscription | None,
    ) -> int | None:
        included = entitlements.member_limit
        if included is None:
            return None
        if plan != "pro" or not subscription:
            return included
        purchased = max(subscription.additional_member_seats or 0, 0)
        return min(included + purchased, PLAN_MAX_MEMBER_LIMIT[plan])

    @classmethod
    def effective_status(
        cls,
        subscription: BusinessSubscription | None,
    ) -> str:
        if not subscription:
            return "active"
        if (
            subscription.status == "trialing"
            and cls.effective_plan(subscription) == "free"
        ):
            return "expired"
        if (
            subscription.status == "active"
            and cls.effective_plan(subscription) == "free"
        ):
            return "expired"
        return subscription.status

    @classmethod
    def entitlements_for_business(
        cls,
        business_id: str,
        db: Session,
    ) -> tuple[PlanName, PlanEntitlements, BusinessSubscription | None]:
        subscription = cls.subscription_for_business(business_id, db)
        plan = cls.effective_plan(subscription)
        return plan, PLAN_ENTITLEMENTS[plan], subscription

    @classmethod
    def require_feature(
        cls,
        business_id: str,
        feature: str,
        db: Session,
    ) -> None:
        plan, entitlements, _ = cls.entitlements_for_business(business_id, db)
        if getattr(entitlements, feature, False):
            return
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "plan_feature_required",
                "feature": feature,
                "current_plan": plan,
                "message": "This feature requires a higher subscription plan.",
            },
        )

    @classmethod
    def require_active_sku_capacity(
        cls,
        business_id: str,
        db: Session,
        additional_skus: int = 1,
    ) -> None:
        plan, entitlements, _ = cls.entitlements_for_business(business_id, db)
        limit = entitlements.active_sku_limit
        if limit is None:
            return
        active_skus = db.execute(
            select(func.count(Product.id)).where(
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        ).scalar_one()
        if active_skus + additional_skus <= limit:
            return
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "active_sku_limit_reached",
                "current_plan": plan,
                "limit": limit,
                "message": f"Your {plan.title()} plan allows up to {limit} active SKUs.",
            },
        )

    @classmethod
    def require_member_capacity(
        cls,
        business_id: str,
        db: Session,
        additional_members: int = 1,
    ) -> None:
        plan, entitlements, subscription = cls.entitlements_for_business(
            business_id,
            db,
        )
        limit = cls.effective_member_limit(
            plan,
            entitlements,
            subscription,
        )
        if limit is None:
            return
        allocated_members = db.execute(
            select(func.count(BusinessMembership.id)).where(
                BusinessMembership.business_id == business_id,
                BusinessMembership.status.in_(("active", "suspended")),
            )
        ).scalar_one()
        pending_invitations = db.execute(
            select(func.count(BusinessInvitation.id)).where(
                BusinessInvitation.business_id == business_id,
                BusinessInvitation.status == "pending",
                BusinessInvitation.expires_at > datetime.now(timezone.utc),
            )
        ).scalar_one()
        allocated_members += pending_invitations
        if allocated_members + additional_members <= limit:
            return
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "member_limit_reached",
                "current_plan": plan,
                "limit": limit,
                "message": (
                    f"Your {plan.title()} plan currently allows " f"{limit} members."
                ),
            },
        )

    @classmethod
    def consume_ai_insight(cls, business_id: str, db: Session) -> None:
        cls.require_feature(business_id, "ai_insights", db)
        plan, entitlements, _ = cls.entitlements_for_business(business_id, db)
        limit = entitlements.ai_insights_weekly
        if limit is None:
            return
        period_start = cls.ai_period_start(business_id, db)
        usage = db.execute(
            select(SubscriptionUsage).where(
                SubscriptionUsage.business_id == business_id,
                SubscriptionUsage.metric == AI_INSIGHT_METRIC,
                SubscriptionUsage.period_start == period_start,
            )
        ).scalar_one_or_none()
        used = usage.quantity if usage else 0
        if used >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "ai_insight_limit_reached",
                    "current_plan": plan,
                    "limit": limit,
                    "message": "Your weekly AI insight allowance has been used.",
                },
            )
        if usage is None:
            usage = SubscriptionUsage(
                business_id=business_id,
                metric=AI_INSIGHT_METRIC,
                period_start=period_start,
                quantity=0,
            )
            db.add(usage)
        usage.quantity += 1
        db.flush()

    @classmethod
    def refund_ai_insight(cls, business_id: str, db: Session) -> None:
        """Release a reservation when the AI provider did not respond."""
        period_start = cls.ai_period_start(business_id, db)
        usage = db.execute(
            select(SubscriptionUsage).where(
                SubscriptionUsage.business_id == business_id,
                SubscriptionUsage.metric == AI_INSIGHT_METRIC,
                SubscriptionUsage.period_start == period_start,
            )
        ).scalar_one_or_none()
        if usage is None or usage.quantity <= 0:
            return
        usage.quantity -= 1
        db.flush()

    @classmethod
    def usage_summary(
        cls,
        business_id: str,
        db: Session,
        user_id: str | None = None,
    ) -> dict:
        plan, entitlements, subscription = cls.entitlements_for_business(
            business_id,
            db,
        )
        period_start = cls.ai_period_start(business_id, db)
        ai_used = (
            db.execute(
                select(SubscriptionUsage.quantity).where(
                    SubscriptionUsage.business_id == business_id,
                    SubscriptionUsage.metric == AI_INSIGHT_METRIC,
                    SubscriptionUsage.period_start == period_start,
                )
            ).scalar_one_or_none()
            or 0
        )
        active_skus = db.execute(
            select(func.count(Product.id)).where(
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        ).scalar_one()
        active_members = db.execute(
            select(func.count(BusinessMembership.id)).where(
                BusinessMembership.business_id == business_id,
                BusinessMembership.status == "active",
            )
        ).scalar_one()
        member_limit = cls.effective_member_limit(
            plan,
            entitlements,
            subscription,
        )
        purchased_seats = (
            subscription.additional_member_seats
            if subscription and plan == "pro"
            else 0
        ) or 0
        limits = {
            key: value
            for key, value in asdict(entitlements).items()
            if not isinstance(value, bool)
        }
        limits.update(
            {
                "included_member_limit": entitlements.member_limit,
                "member_limit": member_limit,
                "max_member_limit": PLAN_MAX_MEMBER_LIMIT[plan],
            }
        )
        business_trial_available = plan == "free" and (
            not subscription
            or (subscription.plan == "free" and subscription.trial_started_at is None)
        )
        trial_eligible = bool(
            user_id
            and business_trial_available
            and not cls.user_has_used_pro_trial(user_id, db)
        )
        return {
            "plan": plan,
            "monthly_price_php": PLAN_MONTHLY_PRICE_PHP[plan],
            "additional_member_price_php": (PLAN_ADDITIONAL_MEMBER_PRICE_PHP[plan]),
            "additional_member_seats": purchased_seats,
            "trial_eligible": trial_eligible,
            "status": cls.effective_status(subscription),
            "provider": subscription.provider if subscription else "manual",
            "billing_interval": (
                subscription.billing_interval if subscription else "monthly"
            ),
            "trial_ends_at": subscription.trial_ends_at if subscription else None,
            "current_period_ends_at": (
                subscription.current_period_ends_at if subscription else None
            ),
            "current_period_started_at": (
                subscription.current_period_started_at if subscription else None
            ),
            "cancel_at_period_end": (
                subscription.cancel_at_period_end if subscription else False
            ),
            "limits": limits,
            "features": {
                key: value
                for key, value in asdict(entitlements).items()
                if isinstance(value, bool)
            },
            "usage": {
                "active_skus": active_skus,
                "active_members": active_members,
                "ai_insights": ai_used,
                "ai_period_start": period_start.isoformat(),
            },
        }

    @classmethod
    def assign_plan(
        cls,
        business_id: str,
        plan: PlanName,
        status_value: str,
        db: Session,
        *,
        provider: str = "manual",
        trial_ends_at=None,
        current_period_started_at=None,
        current_period_ends_at=None,
        additional_member_seats: int | None = None,
        billing_interval: str = "monthly",
    ) -> BusinessSubscription:
        business = db.execute(
            select(Business.id).where(Business.id == business_id)
        ).scalar_one_or_none()
        if business is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found.",
            )

        subscription = cls.subscription_for_business(business_id, db)
        if subscription is None:
            subscription = BusinessSubscription(business_id=business_id)
            db.add(subscription)
        seat_count = additional_member_seats
        if seat_count is None:
            seat_count = (
                subscription.additional_member_seats or 0 if plan == "pro" else 0
            )
        maximum_additional_seats = (
            PLAN_MAX_MEMBER_LIMIT["pro"] - PLAN_ENTITLEMENTS["pro"].member_limit
        )
        if plan != "pro" and seat_count:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Additional member seats are only available on Pro.",
            )
        if not 0 <= seat_count <= maximum_additional_seats:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Pro supports between 0 and "
                    f"{maximum_additional_seats} additional member seats."
                ),
            )
        if status_value == "trialing" and seat_count:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Additional member seats cannot be added to a trial.",
            )
        subscription.plan = plan
        subscription.status = status_value
        subscription.provider = provider
        subscription.billing_interval = billing_interval
        subscription.additional_member_seats = seat_count
        if status_value == "trialing" and trial_ends_at:
            subscription.trial_started_at = (
                subscription.trial_started_at or datetime.now(timezone.utc)
            )
        subscription.trial_ends_at = trial_ends_at
        subscription.current_period_started_at = current_period_started_at
        subscription.current_period_ends_at = current_period_ends_at
        db.flush()
        return subscription

    @classmethod
    def start_pro_trial(
        cls,
        business_id: str,
        user_id: str,
        db: Session,
    ) -> BusinessSubscription:
        user = db.execute(
            select(User).where(User.id == user_id).with_for_update()
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )
        if user.pro_trial_used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "user_trial_already_used",
                    "message": ("Your account has already used its Pro trial."),
                },
            )
        subscription = cls.subscription_for_business(business_id, db)
        if subscription and subscription.trial_started_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "trial_already_used",
                    "message": "This business has already used its Pro trial.",
                },
            )
        if subscription and subscription.plan != "free":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "trial_not_available",
                    "message": ("A trial cannot start after selecting a paid plan."),
                },
            )

        now = datetime.now(timezone.utc)
        if subscription is None:
            subscription = BusinessSubscription(business_id=business_id)
            db.add(subscription)
        subscription.plan = "pro"
        subscription.status = "trialing"
        subscription.provider = "manual"
        subscription.additional_member_seats = 0
        subscription.trial_started_at = now
        subscription.trial_ends_at = now + timedelta(days=PRO_TRIAL_DAYS)
        subscription.current_period_ends_at = None
        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None
        user.pro_trial_used_at = now
        db.add(user)
        db.flush()
        return subscription
