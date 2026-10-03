"""
Task — a unit of work derived from an agent decision or human action.

Lifecycle (status enum):
    pending_approval → approved → dispatched → acked → done
                    ↘ rejected                      ↘ failed
                    ↘ cancelled

Key invariants:
- Every task has an idempotency_key. Dispatch uses it to ensure retries
  never double-actuate hardware.
- Every task links to the audit_log entry that caused it (source_audit_id).
  So we can always trace "why does this task exist?" back to the decision.
- Timestamps record every state transition. state_history is not stored
  separately — the audit log has it, and timestamps here tell the quick story.
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    func,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskStatus(str, enum.Enum):
    """States a task can be in. Transitions are enforced in the service layer."""
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISPATCHED = "dispatched"
    ACKED = "acked"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Tools that can be the target of a task.
# Must stay in sync with gate.KNOWN_TOOLS.
TASK_TOOLS = frozenset({
    "control_irrigation",
    "schedule_fertigation",
    "spray_chemical",
})


class Task(Base):
    __tablename__ = "tasks"

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
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The action
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Lifecycle
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.PENDING_APPROVAL,
        index=True,
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Idempotency — the dispatch layer uses this to prevent double-actuation
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )

    # Traceability — link back to the audit_log entry that created this task
    source_audit_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_log.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Actor info
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps for each transition
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Free-form result/error blob
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<Task {self.tool} status={self.status.value} plot={self.plot_id}>"