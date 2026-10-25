"""
Pydantic schemas for sensor readings.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# Canonical metric names.
VALID_METRICS = {
    "soil_moisture",   # volumetric water content (0.0–1.0)
    "temperature",     # °C
    "humidity",        # relative humidity (0.0–1.0)
    "ec",              # electrical conductivity (mS/cm)
    "ph",              # pH
    "light",           # lux
    "co2",             # ppm
    "pump_state",      # 0 = OFF, 1 = ON
    "valve_state",     # 0 = CLOSED, 1 = OPEN
}

class ReadingCreate(BaseModel):
    """Payload a device sends. `time` is optional — defaults to server now."""
    metric: str = Field(..., min_length=1, max_length=32)
    value: float
    time: datetime | None = None
    # Allows the Hub to forward data on behalf of a satellite
    source_device_serial: str | None = None

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

class SummaryBucket(BaseModel):
    """One aggregated data point — used by the summary endpoint."""
    bucket: datetime
    device_id: uuid.UUID
    metric: str
    avg_value: float
    min_value: float
    max_value: float
    sample_count: int