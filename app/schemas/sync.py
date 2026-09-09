from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SyncMutation(BaseModel):
    client_event_id: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any]
    occurred_at: datetime


class SyncMutationResponse(BaseModel):
    success: bool = True
    duplicate: bool = False
    client_event_id: str
    type: str
    result: dict[str, Any] | None = None