from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import RequestContext, require_permission
from app.schemas.intelligence import (
    AskIntelligenceRequest,
    IntelligenceResponse,
    ReportSummaryRequest,
)
from app.services.intelligence import IntelligenceService


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.post("/ask", response_model=IntelligenceResponse)
async def ask_intelligence(
    payload: AskIntelligenceRequest,
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return await IntelligenceService.ask(
        str(context.business_id), payload.question, db
    )


@router.get(
    "/forecasts/{product_id}/explanation",
    response_model=IntelligenceResponse,
)
async def explain_forecast(
    product_id: str,
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return await IntelligenceService.explain_forecast(
        str(context.business_id), product_id, db
    )


@router.get(
    "/anomalies/{anomaly_id}/explanation",
    response_model=IntelligenceResponse,
)
async def explain_anomaly(
    anomaly_id: str,
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return await IntelligenceService.explain_anomaly(
        str(context.business_id), anomaly_id, db
    )


@router.post("/reports/summary", response_model=IntelligenceResponse)
async def summarize_report(
    payload: ReportSummaryRequest,
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    return await IntelligenceService.summarize_report(
        str(context.business_id), payload.report, payload.period, db
    )
