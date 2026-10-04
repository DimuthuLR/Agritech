"""
Pydantic schemas for the Task resource.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from app.db.models.task import TaskStatus


class TaskRead(BaseModel):
    """
    Public view of a task. Status is serialized as the enum's value
    (e.g. 'pending_approval'), which is what the frontend expects.
    """
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plot_id: uuid.UUID
    device_id: uuid.UUID | None

    tool: str
    args: dict
    reason: str
    status: TaskStatus
    requires_approval: bool
    idempotency_key: uuid.UUID
    created_by: str | None

    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    acked_at: datetime | None
    completed_at: datetime | None

    result: dict | None


class TaskReject(BaseModel):
    """Body for POST /tasks/{id}/reject."""
    reason: str = Field(..., min_length=1, max_length=500)