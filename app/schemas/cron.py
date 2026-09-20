from pydantic import BaseModel


class WeeklySummaryJobResponse(BaseModel):
    due: int
    sent: int
    failed: int
    skipped_not_entitled: int
    would_send: int
