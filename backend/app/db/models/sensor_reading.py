"""
SensorReading — hypertable of raw time-series readings.

The composite primary key (time, device_id, metric) is required by TimescaleDB:
the partitioning column (`time`) must be part of any unique constraint.

Alembic creates the table normally; a follow-up SQL statement converts it into
a hypertable partitioned by `time`.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    # Timescale requires the partition column (time) in the PK.
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(
        String(32), primary_key=True, nullable=False
    )

    # tenant_id and plot_id are denormalized for fast tenant-scoped queries —
    # avoiding a join to `devices` in the hot path.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    plot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    value: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<SensorReading {self.metric}={self.value} at {self.time}>"