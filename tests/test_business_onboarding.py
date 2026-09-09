from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.models import BusinessSubscription
from app.schemas.business import BusinessCreate, BusinessProfileUpdate
from app.services.business import BusinessService


def profile_payload(**overrides):
    values = {
        "name": "Demo Store",
        "industry": "Retail",
        "email": "",
        "phone": "12345",
        "address": "Main Street",
        "currency_code": "usd",
        "timezone": "America/New_York",
        "complete_onboarding": True,
    }
    values.update(overrides)
    return BusinessProfileUpdate(**values)


def test_business_profile_normalizes_optional_fields():
    payload = profile_payload()

    assert payload.email is None
    assert payload.currency_code == "USD"


def test_business_create_normalizes_name():
    payload = BusinessCreate(name="  Second Store  ")

    assert payload.name == "Second Store"


def test_business_profile_rejects_unknown_timezone():
    with pytest.raises(ValidationError):
        profile_payload(timezone="Unknown/Timezone")


def test_completing_profile_marks_business_onboarded():
    business = SimpleNamespace(
        onboarding_completed=False,
        onboarding_completed_at=None,
    )
    database = SimpleNamespace(
        commit=lambda: None,
        refresh=lambda value: None,
    )

    result = BusinessService.update_profile(
        business,
        profile_payload(),
        database,
    )

    assert result.onboarding_completed is True
    assert result.onboarding_completed_at is not None
    assert result.currency_code == "USD"


def test_new_business_receives_pro_trial_without_timezone_collision():
    query = MagicMock()
    query.filter.return_value.first.return_value = None
    query.filter.return_value.all.return_value = []
    query.filter.return_value.update.return_value = 1
    query.all.return_value = []
    database = MagicMock()
    database.query.return_value = query

    BusinessService.create_business(
        "user-id",
        "Sari sari store",
        "sari-sari-store",
        "PHP",
        "Asia/Manila",
        database,
        commit=False,
        grant_pro_trial=True,
    )

    added = [call.args[0] for call in database.add.call_args_list]
    subscription = next(
        item for item in added if isinstance(item, BusinessSubscription)
    )
    assert subscription.plan == "pro"
    assert subscription.status == "trialing"
    assert subscription.trial_started_at is not None
    assert subscription.trial_ends_at is not None


def test_additional_business_starts_on_free():
    query = MagicMock()
    query.filter.return_value.first.return_value = None
    query.filter.return_value.all.return_value = []
    query.all.return_value = []
    database = MagicMock()
    database.query.return_value = query

    BusinessService.create_business(
        "user-id",
        "Second store",
        "second-store",
        "PHP",
        "Asia/Manila",
        database,
        commit=False,
    )

    added = [call.args[0] for call in database.add.call_args_list]
    subscription = next(
        item for item in added if isinstance(item, BusinessSubscription)
    )
    assert subscription.plan == "free"
    assert subscription.status == "active"
    assert subscription.trial_started_at is None
