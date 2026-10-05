"""
Pydantic schemas for FieldEvent resources.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from app.db.models.field_event import (
    FieldEventType,
    FieldEventOutcome,
)


class FieldEventCreate(BaseModel):
    """Body for POST /field-events/override."""
    plot_id: uuid.UUID
    action_taken: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=500)
    forecast_mm: float | None = Field(None, ge=0)
    forecast_window_hours: int = Field(6, ge=1, le=48)


class FieldEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plot_id: uuid.UUID
    event_type: FieldEventType
    action_taken: str | None
    reported_by: str
    weather_forecast_mm: float | None
    weather_actual_mm: float | None
    forecast_window_hours: int | None
    reason: str | None
    outcome: FieldEventOutcome | None
    details: dict
    occurred_at: datetime
    verified_at: datetime | None
    created_at: datetime