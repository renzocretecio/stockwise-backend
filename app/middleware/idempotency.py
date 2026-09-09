import hashlib

from fastapi import Request
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.config.database import SessionLocal
from app.models.idempotency import IdempotencyRequest


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _request_scope(request: Request) -> str:
    business_id = request.headers.get("X-Business-ID", "")
    authorization = request.headers.get("Authorization", "")
    token_hash = hashlib.sha256(authorization.encode()).hexdigest()
    return hashlib.sha256(
        f"{business_id}:{token_hash}:{request.url.path}".encode()
    ).hexdigest()


def _fingerprint(request: Request, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(request.method.encode())
    digest.update(b"\0")
    digest.update(request.url.path.encode())
    digest.update(b"\0")
    digest.update(body)
    return digest.hexdigest()


async def idempotency_middleware(request: Request, call_next):
    if request.method not in MUTATING_METHODS:
        return await call_next(request)

    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        return await call_next(request)

    body = await request.body()
    scope = _request_scope(request)
    fingerprint = _fingerprint(request, body)
    db = SessionLocal()
    record = None
    try:
        record = db.execute(
            select(IdempotencyRequest).where(
                IdempotencyRequest.request_scope == scope,
                IdempotencyRequest.idempotency_key == key,
            )
        ).scalar_one_or_none()
        if record:
            if record.request_fingerprint != fingerprint:
                return Response(
                    content='{"detail":"Idempotency-Key was already used with a different request"}',
                    status_code=409,
                    media_type="application/json",
                )
            if record.response_status is None:
                return Response(
                    content='{"detail":"A request with this Idempotency-Key is already in progress"}',
                    status_code=409,
                    media_type="application/json",
                )
            return Response(
                content=record.response_body or "",
                status_code=record.response_status,
                headers={
                    "content-type": record.response_content_type
                    or "application/json"
                },
            )

        record = IdempotencyRequest(
            request_scope=scope,
            idempotency_key=key,
            request_fingerprint=fingerprint,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            record = db.execute(
                select(IdempotencyRequest).where(
                    IdempotencyRequest.request_scope == scope,
                    IdempotencyRequest.idempotency_key == key,
                )
            ).scalar_one()
            if record.request_fingerprint != fingerprint:
                return Response(
                    content='{"detail":"Idempotency-Key was already used with a different request"}',
                    status_code=409,
                    media_type="application/json",
                )
            return Response(
                content='{"detail":"A request with this Idempotency-Key is already in progress"}',
                status_code=409,
                media_type="application/json",
            )

        response = await call_next(request)
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
        record.response_status = response.status_code
        record.response_body = response_body.decode("utf-8")
        record.response_content_type = response.headers.get("content-type")
        db.add(record)
        db.commit()
        return Response(
            content=response_body,
            status_code=response.status_code,
            headers={
                "content-type": response.headers.get("content-type", "application/json"),
            },
        )
    except Exception:
        if record is not None and record.response_status is None:
            db.delete(record)
            db.commit()
        raise
    finally:
        db.close()