import json
from types import SimpleNamespace

import pytest

from app.middleware import idempotency as middleware


class FakeQuery:
    def __init__(self, record):
        self.record = record

    def where(self, *conditions):
        return self


class FakeDatabase:
    def __init__(self):
        self.record = None
        self.deleted = False

    def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.record, scalar_one=lambda: self.record)

    def add(self, record):
        self.record = record

    def commit(self):
        return None

    def rollback(self):
        return None

    def delete(self, record):
        self.deleted = True
        self.record = None

    def close(self):
        return None


class FakeResponse:
    status_code = 201
    headers = {"content-type": "application/json"}

    async def iterator(self):
        yield b'{"created":true}'

    @property
    def body_iterator(self):
        return self.iterator()


class FakeRequest:
    method = "POST"
    headers = {
        "Idempotency-Key": "offline-sale-1",
        "X-Business-ID": "business-1",
        "Authorization": "Bearer token",
    }

    class URL:
        path = "/api/v1/sales"

    url = URL()

    async def body(self):
        return b'{"total_amount":100}'


@pytest.mark.asyncio
async def test_idempotency_stores_first_response(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(middleware, "SessionLocal", lambda: database)

    response = await middleware.idempotency_middleware(
        FakeRequest(), lambda request: _response()
    )

    assert response.status_code == 201
    assert database.record.response_body == '{"created":true}'
    assert database.record.request_fingerprint


@pytest.mark.asyncio
async def test_idempotency_replays_completed_response(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(middleware, "SessionLocal", lambda: database)
    await middleware.idempotency_middleware(FakeRequest(), lambda request: _response())

    replay = await middleware.idempotency_middleware(
        FakeRequest(), lambda request: pytest.fail("request must not execute twice")
    )

    assert replay.status_code == 201
    assert replay.body == b'{"created":true}'


@pytest.mark.asyncio
async def test_idempotency_rejects_same_key_with_different_payload(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(middleware, "SessionLocal", lambda: database)
    await middleware.idempotency_middleware(FakeRequest(), lambda request: _response())

    class DifferentRequest(FakeRequest):
        async def body(self):
            return json.dumps({"total_amount": 200}).encode()

    conflict = await middleware.idempotency_middleware(
        DifferentRequest(), lambda request: pytest.fail("conflict must not execute")
    )

    assert conflict.status_code == 409


async def _response():
    return FakeResponse()