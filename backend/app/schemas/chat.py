from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ChatStatus = Literal[
    "completed",
    "clarification_required",
    "approval_required",
]


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str = Field(min_length=1)


class PendingApprovalResponse(BaseModel):
    approval_id: str
    deletion_request_id: str
    task_id: str
    message: str


class ChatResponse(BaseModel):
    thread_id: str
    message_id: str
    status: ChatStatus
    assistant_message: str
    pending_approval: PendingApprovalResponse | None = None


class ApprovalRequest(BaseModel):
    approval_id: str
    decision: Literal["approve", "reject"]

class ApprovalResponse(BaseModel):
    thread_id: str
    approval_id: str
    status: Literal["completed"]
    assistant_message: str


class HistoryMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[HistoryMessage]
    next_cursor: str | None
    has_more: bool