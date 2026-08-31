import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routes import auth
from app.schemas.auth import SignUpWithBusinessRequest


def signup_request(**overrides):
    values = {
        "email": " Owner@Example.com ",
        "password": "secure-password",
        "first_name": "Owner",
        "last_name": "User",
        "business_name": "Acme Store",
    }
    values.update(overrides)
    return SignUpWithBusinessRequest(**values)


def test_signup_request_uses_hidden_business_defaults():
    request = signup_request()

    assert request.email == "owner@example.com"
    assert request.business_slug is None
    assert request.currency_code == "PHP"
    assert request.timezone == "Asia/Manila"


def test_signup_request_rejects_invalid_timezone():
    with pytest.raises(ValidationError):
        signup_request(timezone="Not/A_Timezone")


def test_business_slug_is_generated_and_deduplicated():
    query = MagicMock()
    query.filter.return_value.first.side_effect = [object(), None]
    database = SimpleNamespace(query=lambda model: query)

    slug = auth.BusinessService.generate_unique_slug(
        "Café & Grocery!",
        database,
    )

    assert slug == "cafe-grocery-2"


def test_signup_rolls_back_when_business_creation_fails(monkeypatch):
    database = SimpleNamespace(
        commit=lambda: pytest.fail("commit must not be called"),
        rollback_called=False,
    )

    def rollback():
        database.rollback_called = True

    database.rollback = rollback
    monkeypatch.setattr(
        auth.AuthService,
        "register",
        lambda *args, **kwargs: {
            "user": {"id": str(uuid4())},
            "access_token": "token",
        },
    )

    def fail_business(*args, **kwargs):
        raise ValueError("duplicate slug")

    monkeypatch.setattr(
        auth.BusinessService,
        "create_business",
        fail_business,
    )
    monkeypatch.setattr(
        auth.BusinessService,
        "generate_unique_slug",
        lambda *args: "acme-store",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(auth.signup(signup_request(), database))

    assert error.value.status_code == 400
    assert error.value.detail == "Unable to create account"
    assert database.rollback_called is True
