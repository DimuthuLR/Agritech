"""
FieldEvent — farmer-reported or system-verified events on a plot.

Purpose: capture when a farmer acts against the platform's advice
(override), and later verify whether the decision turned out to be
right. Feeds the AI's RAG context so it can reason about how reliable
forecasts/advice have been on this specific plot.

Event types:
- OVERRIDE:     farmer did something the gate had suppressed
- OUTCOME:      farmer reports the result of a past action
- OBSERVATION:  farmer notes something (no gate relation)

The AI never modifies the gate based on these events. It only *sees*
them in its reasoning context. Gate changes require a human (Layer 3).
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Float, Integer, func, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FieldEventType(str, enum.Enum):
    OVERRIDE = "override"
    OUTCOME = "outcome"
    OBSERVATION = "observation"


class FieldEventOutcome(str, enum.Enum):
    WORKED = "worked"
    FAILED = "failed"
    UNKNOWN = "unknown"


class FieldEvent(Base):
    __tablename__ = "field_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[FieldEventType] = mapped_column(
        SAEnum(FieldEventType, name="field_event_type"),
        nullable=False,
        index=True,
    )

    # What action was taken (tool name), e.g. 'spray_chemical'
    action_taken: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Links back to the platform artifacts this event relates to
    related_audit_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_log.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("diagnoses.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Who reported it: 'farmer:<uuid>', 'system:archive_check', 'system:manual'
    reported_by: Mapped[str] = mapped_column(String(128), nullable=False)

    # Weather context at the time
    weather_forecast_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_actual_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_window_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Farmer's reason, and later verified outcome
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[FieldEventOutcome | None] = mapped_column(
        SAEnum(FieldEventOutcome, name="field_event_outcome"),
        nullable=True,
    )

    # Free-form extras
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Timing
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<FieldEvent {self.event_type.value} "
            f"action={self.action_taken!r} plot={self.plot_id}>"
        )