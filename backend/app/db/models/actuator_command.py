"""
ActuatorCommand — every hardware command sent, with idempotency and ack.

One task can produce multiple actuator_commands (e.g. a multi-valve
irrigation becomes one command per valve). Commands are the atomic
unit of hardware interaction; tasks are the logical unit of work.

The idempotency_key is the safety net: if we retry a dispatch, the
device or gateway can check whether it already saw this key and refuse
to act twice.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActuatorCommand(Base):
    __tablename__ = "actuator_commands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Transport
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Idempotency — the same key prevents double-actuation on retries
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )

    # Timeline
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Response
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ActuatorCommand topic={self.topic!r} task={self.task_id}>"