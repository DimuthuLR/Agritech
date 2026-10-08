"""
Pydantic schemas for chat endpoints.

Chat operates in two modes:
  - Stateless: caller passes `history` explicitly (legacy, still supported)
  - Session: caller passes `session_id`; history lives in the DB

Session mode is preferred for anything longer than one exchange. It
enables persistence, audit, and the live-state reconciliation logic
that keeps chat answers consistent with the task table.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)
    created_at: datetime | None = None


class ChatRequest(BaseModel):
    """
    Send a message to the assistant.

    - If `session_id` is provided, `history` is ignored. History is
      loaded from the DB, the new turn is appended, and the response
      includes the updated session_id.
    - If `session_id` is absent, the caller must provide `history` to
      maintain continuity. This is the legacy stateless mode.
    """
    message: str = Field(..., min_length=1, max_length=4000)
    plot_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str
    session_id: uuid.UUID | None = None
    message_count: int | None = None


class ChatSessionCreate(BaseModel):
    title: str | None = Field(None, max_length=200)
    plot_id: uuid.UUID | None = None


class ChatSessionUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    is_archived: bool | None = None


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    plot_id: uuid.UUID | None
    title: str | None
    message_count: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


class ChatSessionWithMessages(ChatSessionRead):
    messages: list[ChatMessage]