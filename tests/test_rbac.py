from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.config.rbac import PERMISSIONS, SYSTEM_ROLE_PERMISSIONS
from app.services.members import MemberService


def test_owner_role_includes_every_registered_permission():
    assert SYSTEM_ROLE_PERMISSIONS["owner"] == set(PERMISSIONS)


def test_operational_roles_do_not_receive_owner_only_access():
    for role_name in ("manager", "cashier", "stock clerk"):
        permissions = SYSTEM_ROLE_PERMISSIONS[role_name]
        assert "billing.manage" not in permissions
        assert "business.update" not in permissions


def test_cashier_can_create_sales_but_cannot_adjust_inventory():
    cashier = SYSTEM_ROLE_PERMISSIONS["cashier"]
    assert "sales.create" in cashier
    assert "sales.return" in cashier
    assert "inventory.adjust" not in cashier


def test_only_operational_leaders_export_reports_by_default():
    assert "reports.export" in SYSTEM_ROLE_PERMISSIONS["owner"]
    assert "reports.export" in SYSTEM_ROLE_PERMISSIONS["manager"]
    assert "reports.export" not in SYSTEM_ROLE_PERMISSIONS["cashier"]
    assert "reports.export" not in SYSTEM_ROLE_PERMISSIONS["stock clerk"]


def test_invitation_tokens_are_stored_as_one_way_hashes():
    token = "example-invitation-token"
    hashed = MemberService.token_hash(token)

    assert hashed != token
    assert len(hashed) == 64
    assert hashed == MemberService.token_hash(token)


def test_invitation_expiration_supports_aware_and_legacy_naive_dates():
    now = datetime.now(timezone.utc)

    assert MemberService.is_expired(now - timedelta(seconds=1), now)
    assert not MemberService.is_expired(now + timedelta(seconds=1), now)
    assert MemberService.is_expired(
        (now - timedelta(seconds=1)).replace(tzinfo=None),
        now,
    )


def test_custom_roles_cannot_receive_owner_only_permissions():
    with pytest.raises(HTTPException) as error:
        MemberService.validate_custom_permissions(["billing.manage"])

    assert error.value.status_code == 422
