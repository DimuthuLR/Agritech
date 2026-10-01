"""
Pydantic schemas for Farm resources.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class FarmBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    region: str = Field("EU", max_length=16)
    timezone: str = Field("UTC", max_length=64)


class FarmCreate(FarmBase):
    """tenant_id is NOT a field — it's assigned by the server from the caller's token."""


class FarmRead(FarmBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class FarmUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    region: str | None = Field(None, max_length=16)
    timezone: str | None = Field(None, max_length=64)