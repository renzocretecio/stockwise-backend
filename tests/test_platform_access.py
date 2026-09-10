from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config.settings import settings
from app.core.platform_access import is_superadmin_user, require_superadmin


def test_database_superadmin_is_authorized(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ADMIN_EMAILS", "")
    user = SimpleNamespace(
        email="admin@example.com",
        is_superadmin=True,
    )

    assert is_superadmin_user(user) is True
    assert require_superadmin(user) is user


def test_allowlist_remains_a_bootstrap_fallback(monkeypatch):
    monkeypatch.setattr(
        settings,
        "BILLING_ADMIN_EMAILS",
        "bootstrap@example.com",
    )
    user = SimpleNamespace(
        email="BOOTSTRAP@example.com",
        is_superadmin=False,
    )

    assert is_superadmin_user(user) is True


def test_normal_user_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ADMIN_EMAILS", "")
    user = SimpleNamespace(
        email="owner@example.com",
        is_superadmin=False,
    )

    with pytest.raises(HTTPException) as error:
        require_superadmin(user)

    assert error.value.status_code == 403
