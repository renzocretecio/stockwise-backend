from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import auth
from app.services.auth import AuthService


class GoogleResponse:
    def __init__(self, payload: dict, success: bool = True):
        self.payload = payload
        self.is_success = success

    def json(self) -> dict:
        return self.payload


class GoogleClient:
    def __init__(self, profile: dict):
        self.profile = profile

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return GoogleResponse({"access_token": "google-access-token"})

    async def get(self, *_args, **_kwargs):
        return GoogleResponse(self.profile)


def configure_google(monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        auth.settings,
        "GOOGLE_REDIRECT_URI",
        "http://localhost:3000/api/auth/google/callback",
    )


@pytest.mark.asyncio
async def test_google_login_rejects_an_unapproved_redirect(monkeypatch):
    configure_google(monkeypatch)

    with pytest.raises(HTTPException) as error:
        await AuthService.login_with_google(
            "code",
            "a" * 43,
            "https://attacker.example/callback",
            object(),
        )

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_google_login_requires_a_verified_email(monkeypatch):
    configure_google(monkeypatch)
    client = GoogleClient(
        {
            "sub": "google-user-1",
            "email": "owner@example.com",
            "email_verified": False,
        }
    )
    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **_kwargs: client,
    )

    with pytest.raises(HTTPException) as error:
        await AuthService.login_with_google(
            "code",
            "a" * 43,
            "http://localhost:3000/api/auth/google/callback",
            object(),
        )

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_google_login_creates_a_user_from_verified_profile(monkeypatch):
    configure_google(monkeypatch)
    client = GoogleClient(
        {
            "sub": "google-user-1",
            "email": " Owner@Example.com ",
            "email_verified": True,
            "given_name": "Renzo",
            "family_name": "Santos",
        }
    )
    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **_kwargs: client,
    )

    query = SimpleNamespace(
        filter=lambda *_args, **_kwargs: SimpleNamespace(
            first=lambda: None,
        )
    )
    added = []

    def add(value):
        added.append(value)

    def flush():
        if added and added[-1].id is None:
            added[-1].id = uuid4()

    database = SimpleNamespace(
        query=lambda _model: query,
        add=add,
        flush=flush,
        commit=lambda: None,
        refresh=lambda _value: None,
    )

    result = await AuthService.login_with_google(
        "code",
        "a" * 43,
        "http://localhost:3000/api/auth/google/callback",
        database,
    )

    assert result["is_new_user"] is True
    assert result["user"]["email"] == "owner@example.com"
    assert result["access_token"]
    assert added[0].google_subject == "google-user-1"
