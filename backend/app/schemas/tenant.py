"""
Pydantic schemas for Tenant resources.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
        description="URL-friendly identifier: lowercase letters, digits, and hyphens.",
    )
    region: str = Field("EU", max_length=16)
    timezone: str = Field("UTC", max_length=64)


class TenantCreate(TenantBase):
    pass


class TenantRead(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    region: str | None = Field(None, max_length=16)
    timezone: str | None = Field(None, max_length=64)
    is_active: bool | None = None