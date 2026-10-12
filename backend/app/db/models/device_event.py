"""
DeviceEvent — one row per notable device-originated message.

Every ack, error, boot, or firmware event publishes to an MQTT topic.
The backend subscribes, converts each message to a row here, and the
Devices UI shows them as activity history.

Not to be confused with FieldEvent (farmer overrides) or AuditLog
(safety-critical platform decisions).
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceEvent(Base):
    __tablename__ = "device_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )

    # "ack" | "error" | "boot" | "ota" | "info"
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Ack-specific fields
    cmd_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_device_events_device_occurred", "device_id", "occurred_at"),
        Index("ix_device_events_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_device_events_cmd_id", "cmd_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceEvent {self.event_type!r} device={self.device_id} "
            f"status={self.status}>"
        )