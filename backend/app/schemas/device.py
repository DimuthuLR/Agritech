"""
Pydantic schemas for Device resources.

Important: `secret_key` is returned ONLY on create (and rotate-secret).
It is never included in DeviceRead.
"""
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class DeviceBase(BaseModel):
    kind: str = Field(..., pattern="^(sensor|actuator|gateway)$")
    model: str | None = Field(None, max_length=120)
    serial: str = Field(..., min_length=1, max_length=120)
    firmware: str | None = Field(None, max_length=64)
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceCreate(DeviceBase):
    """plot_id is optional — devices can be unassigned until installed."""
    plot_id: uuid.UUID | None = None


class DeviceRead(BaseModel):
    """Public view. NEVER includes secret_key."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    plot_id: uuid.UUID | None
    kind: str
    model: str | None
    serial: str
    firmware: str | None
    is_active: bool
    metadata: dict[str, Any]
    last_seen_at: datetime | None
    created_at: datetime


class DeviceCreated(DeviceRead):
    """
    Response for POST /devices. Contains the raw secret_key — the ONLY
    time it's ever exposed by the API. Caller must save it immediately.
    """
    secret_key: str


class DeviceUpdate(BaseModel):
    model: str | None = None
    firmware: str | None = None
    plot_id: uuid.UUID | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class DeviceSecretResponse(BaseModel):
    """Response for POST /devices/{id}/rotate-secret."""
    id: uuid.UUID
    secret_key: str