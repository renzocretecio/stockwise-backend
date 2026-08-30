from types import SimpleNamespace
from uuid import uuid4

from app.routes.auth import get_user_profile


def test_get_user_profile_includes_permissions():
    user = SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        first_name="Test",
        last_name="User",
    )
    business = SimpleNamespace(id=uuid4(), name="Acme", slug="acme")
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
