from types import SimpleNamespace

import pytest
from pydantic import ValidationError

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
