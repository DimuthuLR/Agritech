"""
Pydantic schemas for Plot resources.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from app.core.safety.context import SoilType


# Soil types as string values for the API (lowercase, snake_case)
SOIL_TYPE_VALUES = tuple(s.value for s in SoilType)


class PlotBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    area_ha: float = Field(0.0, ge=0.0)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    crop: str | None = Field(None, max_length=64)
    stage: str | None = Field(None, max_length=32)
    soil_type: SoilType = Field(
        ...,
        description="Soil type or growing medium. Required at creation.",
    )


class PlotCreate(PlotBase):
    """
    farm_id is required from the client, but the server verifies that the
    farm belongs to the caller's tenant before accepting it.
    tenant_id is NOT a field — assigned server-side from the caller's token.
    """
    farm_id: uuid.UUID


class PlotRead(PlotBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    farm_id: uuid.UUID
    created_at: datetime


class PlotUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    area_ha: float | None = Field(None, ge=0.0)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    crop: str | None = Field(None, max_length=64)
    stage: str | None = Field(None, max_length=32)
    soil_type: SoilType | None = None