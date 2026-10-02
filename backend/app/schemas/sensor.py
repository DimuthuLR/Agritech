"""
Pydantic schemas for sensor readings.

`ReadingCreate` is what the device sends (or that we simulate).
`ReadingRead` is what a tenant user sees when they query readings.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# Canonical metric names. Keep this in sync with the safety layer (Phase 4).
VALID_METRICS = {
    "soil_moisture",   # volumetric water content (0.0–1.0)
    "temperature",     # °C
    "humidity",        # relative humidity (0.0–1.0)
    "ec",              # electrical conductivity (mS/cm) — nutrient strength
    "ph",              # pH
    "light",           # lux
    "co2",             # ppm
}


class ReadingCreate(BaseModel):
    """Payload a device sends. `time` is optional — defaults to server now."""
    metric: str = Field(..., min_length=1, max_length=32)
    value: float
    time: datetime | None = None


class ReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: datetime
    device_id: uuid.UUID
    metric: str
    tenant_id: uuid.UUID
    plot_id: uuid.UUID | None
    value: float


class IngestAck(BaseModel):
    """Terse success response for high-frequency ingest."""
    status: str = "accepted"
    time: datetime