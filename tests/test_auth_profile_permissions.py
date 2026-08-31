from types import SimpleNamespace
from uuid import uuid4

from app.routes.auth import get_user_profile
from app.routes.auth import update_user_profile
from app.schemas.auth import UserProfileUpdate


def test_get_user_profile_includes_permissions():
    user = SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        first_name="Test",
        last_name="User",
    )
    business = SimpleNamespace(
        id=uuid4(),
        name="Acme",
        slug="acme",
        currency_code="USD",
    )
    role = SimpleNamespace(name="Owner")
    membership = SimpleNamespace(
        user_id=user.id,
        business_id=business.id,
        business=business,
        role=role,
        role_id=uuid4(),
        status="active",
    )

    def fake_query(model):
        if (
            model
            == __import__(
                "app.models", fromlist=["BusinessMembership"]
            ).BusinessMembership
        ):
            return SimpleNamespace(
                filter=lambda *args, **kwargs: SimpleNamespace(
                    all=lambda: [membership]
                )
            )
        if (
            getattr(model, "class_", None)
            == __import__(
                "app.models.permission", fromlist=["Permission"]
            ).Permission
        ):
            return SimpleNamespace(
                join=lambda *args, **kwargs: SimpleNamespace(
                    filter=lambda *args, **kwargs: SimpleNamespace(
                        all=lambda: [("manage_sales",), ("view_products",)]
                    )
                )
            )
        raise AssertionError(f"Unexpected model: {model}")

    db = SimpleNamespace(query=fake_query)

    result = get_user_profile(current_user=user, db=db)

    assert result["user"]["permissions"] == ["manage_sales", "view_products"]
    assert result["businesses"][0]["permissions"] == [
        "manage_sales",
        "view_products",
    ]
    assert result["businesses"][0]["currency_code"] == "USD"


def test_update_user_profile_saves_normalized_names():
    user = SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        first_name="Old",
        last_name="Name",
    )
    database = SimpleNamespace(
        commit=lambda: None,
        refresh=lambda value: None,
    )

    result = update_user_profile(
        UserProfileUpdate(
            first_name="  Updated  ",
            last_name="  User  ",
        ),
        current_user=user,
        db=database,
    )

    assert result["user"]["first_name"] == "Updated"
    assert result["user"]["last_name"] == "User"
