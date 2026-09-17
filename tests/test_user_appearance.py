from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routes.auth import (
    _appearance_update_attempts,
    update_user_appearance,
)
from app.schemas.auth import UserAppearanceUpdate


@pytest.mark.parametrize(
    "palette",
    [
        "petrol",
        "graphite",
        "ocean",
        "amber",
        "rose",
        "custom",
    ],
)
@pytest.mark.parametrize("mode", ["light", "dark", "system"])
def test_saves_appearance_for_authenticated_user(palette, mode):
    user = SimpleNamespace(
        id=uuid4(),
        first_name="Owner",
        appearance_palette="legacy",
        appearance_mode="legacy",
        appearance_custom_color=None,
    )
    db = Mock()
    result = update_user_appearance(
        UserAppearanceUpdate(user_id=user.id, palette=palette, mode=mode),
        current_user=user, db=db,
    )
    assert result["appearance"] == {
        "palette": palette,
        "mode": mode,
        "custom_color": "#245564",
    }
    assert user.appearance_palette == palette
    assert user.appearance_mode == mode
    assert user.appearance_custom_color == "#245564"
    assert user.first_name == "Owner"
    db.commit.assert_called_once()


def test_rejects_stale_offline_preference_after_account_switch():
    db = Mock()
    with pytest.raises(HTTPException) as exc:
        update_user_appearance(
            UserAppearanceUpdate(
                user_id=uuid4(), palette="ocean", mode="dark",
            ),
            current_user=SimpleNamespace(id=uuid4()), db=db,
        )
    assert exc.value.status_code == 403
    db.commit.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("palette", "unknown"), ("mode", "unknown"),
    ("palette", None), ("mode", None),
])
def test_rejects_unsupported_preferences(field, value):
    payload = {"user_id": uuid4(), "palette": "petrol", "mode": "system"}
    payload[field] = value
    with pytest.raises(ValidationError):
        UserAppearanceUpdate(**payload)


def test_rejects_invalid_custom_color():
    with pytest.raises(ValidationError):
        UserAppearanceUpdate(
            user_id=uuid4(),
            palette="custom",
            mode="light",
            custom_color="red",
        )


def test_skips_database_write_when_appearance_is_unchanged():
    user = SimpleNamespace(
        id=uuid4(),
        appearance_palette="ocean",
        appearance_mode="dark",
        appearance_custom_color="#245564",
    )
    db = Mock()

    result = update_user_appearance(
        UserAppearanceUpdate(
            user_id=user.id,
            palette="ocean",
            mode="dark",
        ),
        current_user=user,
        db=db,
    )

    assert result["updated"] is False
    db.commit.assert_not_called()


def test_rate_limits_repeated_appearance_updates():
    user = SimpleNamespace(
        id=uuid4(),
        appearance_palette="legacy",
        appearance_mode="system",
        appearance_custom_color="#245564",
    )
    db = Mock()

    try:
        for index in range(10):
            palette = "petrol" if index % 2 == 0 else "graphite"
            update_user_appearance(
                UserAppearanceUpdate(
                    user_id=user.id,
                    palette=palette,
                    mode="system",
                ),
                current_user=user,
                db=db,
            )

        with pytest.raises(HTTPException) as exc:
            update_user_appearance(
                UserAppearanceUpdate(
                    user_id=user.id,
                    palette="ocean",
                    mode="system",
                ),
                current_user=user,
                db=db,
            )

        assert exc.value.status_code == 429
        assert exc.value.headers.get("Retry-After")
        assert db.commit.call_count == 10
    finally:
        _appearance_update_attempts.pop(str(user.id), None)
