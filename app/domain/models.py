from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RequestStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    sent = "sent"
    failed = "failed"


class RequestIn(BaseModel):
    user_input: str = Field(min_length=1)

    @field_validator("user_input")
    @classmethod
    def not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("user_input cannot be blank")
        return stripped


class RequestCreatedOut(BaseModel):
    id: str


class RequestStatusOut(BaseModel):
    id: str
    status: RequestStatus


class RequestRecord(BaseModel):
    id: str
    user_input: str
    status: RequestStatus = RequestStatus.queued
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
