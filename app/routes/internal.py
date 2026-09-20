import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlmodel import Session

from app.config.database import get_db
from app.config.settings import settings
from app.schemas.cron import WeeklySummaryJobResponse
from app.services.weekly_owner_summary import WeeklyOwnerSummaryService


router = APIRouter(prefix="/internal", tags=["internal"])


def require_cron_secret(
    authorization: str | None = Header(default=None),
) -> None:
    if not settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduled jobs are not configured",
        )

    scheme, _, token = (authorization or "").partition(" ")
    valid_token = scheme == "Bearer" and hmac.compare_digest(
        token,
        settings.CRON_SECRET,
    )
    if not valid_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduled job credentials",
        )


@router.post(
    "/jobs/weekly-owner-summaries",
    response_model=WeeklySummaryJobResponse,
)
async def run_weekly_owner_summaries(
    _: None = Depends(require_cron_secret),
    db: Session = Depends(get_db),
):
    result = await WeeklyOwnerSummaryService.send_due(
        datetime.now(timezone.utc),
        db,
    )
    payload = WeeklySummaryJobResponse(
        due=result.due,
        sent=result.sent,
        failed=result.failed,
        skipped_not_entitled=result.skipped_not_entitled,
        would_send=result.would_send,
    )
    if result.failed:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=payload.model_dump(),
        )
    return payload
