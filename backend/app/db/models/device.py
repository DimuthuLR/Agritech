"""
Device — first-class registry of sensors, actuators, and gateways.

Promoting devices to their own table (instead of just a sensor_id string)
is what enables remote troubleshooting: which device is this, what firmware,
when was it last seen, what's its physical serial number.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        # Fast lookups: "all devices for plot X" and "find by serial"
        Index("ix_devices_plot_kind", "plot_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identity
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # 'sensor' | 'actuator' | 'gateway'
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    firmware: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    secret_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # Operational state
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Flexible attributes: calibration, install notes, hardware revision, etc.
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Device {self.kind} serial={self.serial!r}>"