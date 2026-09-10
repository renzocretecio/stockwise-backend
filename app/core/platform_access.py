from fastapi import Depends, HTTPException, status

from app.config.settings import settings
from app.core.security import get_current_user
from app.models.auth import User


def is_superadmin_user(user: User) -> bool:
    if bool(getattr(user, "is_superadmin", False)):
        return True

    bootstrap_emails = {
        email.strip().lower()
        for email in settings.BILLING_ADMIN_EMAILS.split(",")
        if email.strip()
    }
    return user.email.strip().lower() in bootstrap_emails


def require_superadmin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not is_superadmin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )
    return current_user
