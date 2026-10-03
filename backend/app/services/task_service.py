"""
Task service — the state machine for work items.

A Task is the operational unit derived from an agent decision or human action.
Its lifecycle is enforced here, not in the DB (the DB just has the enum).
Every transition writes to audit_log so the full history is traceable.

Golden rules:
1. Illegal transitions raise. We never silently flip a status.
2. Every transition is audited (actor, from, to, when).
3. Idempotency keys are generated here, once, at task creation.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.safety.audit import write_audit
from app.core.safety.context import SafetyContext
from app.db.models.task import Task, TaskStatus


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TaskError(Exception):
    """Base error for task operations."""


class IllegalTransition(TaskError):
    """Raised when a status change is not allowed by the state machine."""


class TaskNotFound(TaskError):
    """Raised when a task ID doesn't exist."""


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# Map: current_status → set of allowed next statuses
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING_APPROVAL: {
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.APPROVED: {
        TaskStatus.DISPATCHED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.DISPATCHED: {
        TaskStatus.ACKED,
        TaskStatus.FAILED,
    },
    TaskStatus.ACKED: {
        TaskStatus.DONE,
        TaskStatus.FAILED,
    },
    # Terminal states — no outgoing transitions
    TaskStatus.DONE: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.REJECTED: set(),
    TaskStatus.CANCELLED: set(),
}


def _assert_transition(current: TaskStatus, target: TaskStatus) -> None:
    """Raise IllegalTransition if current → target is not allowed."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise IllegalTransition(
            f"Cannot transition from {current.value} to {target.value}"
        )


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _log_transition(
    db: Session,
    task: Task,
    from_status: TaskStatus | None,
    to_status: TaskStatus,
    actor: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write a task.transition audit entry."""
    payload = {
        "task_id": str(task.id),
        "tool": task.tool,
        "from": from_status.value if from_status else None,
        "to": to_status.value,
    }
    if extra:
        payload.update(extra)

    write_audit(
        db,
        kind="task.transition",
        payload=payload,
        actor=actor,
        tenant_id=task.tenant_id,
        target_type="task",
        target_id=str(task.id),
        model=None,
        prompt_version=None,
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def create_task_from_agent(
    db: Session,
    ctx: SafetyContext,
    decision_tool: str,
    decision_args: dict,
    decision_reason: str,
    *,
    requires_approval: bool,
    source_audit_id: int | None = None,
    device_id: uuid.UUID | None = None,
) -> Task:
    """
    Create a Task from an agent decision.

    Status: PENDING_APPROVAL if requires_approval, else APPROVED
    (ready to dispatch).

    Idempotency key: generated once here. The dispatch layer uses it
    to prevent double-actuation on retries.
    """
    # Approval flag determines initial state.
    initial_status = (
        TaskStatus.PENDING_APPROVAL if requires_approval
        else TaskStatus.APPROVED
    )

    task = Task(
        tenant_id=ctx.tenant_id,
        plot_id=ctx.plot_id,
        device_id=device_id,
        tool=decision_tool,
        args=decision_args,
        reason=decision_reason,
        status=initial_status,
        requires_approval=requires_approval,
        idempotency_key=uuid.uuid4(),
        source_audit_id=source_audit_id,
        created_by="agent",
    )
    db.add(task)
    db.flush()  # so task.id is populated before we audit

    _log_transition(
        db,
        task,
        from_status=None,
        to_status=initial_status,
        actor="agent",
        extra={
            "reason": decision_reason,
            "requires_approval": requires_approval,
        },
    )
    db.commit()
    db.refresh(task)
    return task


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

def _get_task(db: Session, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise TaskNotFound(f"Task {task_id} not found")
    return task


def approve_task(
    db: Session,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Task:
    """PENDING_APPROVAL → APPROVED."""
    task = _get_task(db, task_id)
    _assert_transition(task.status, TaskStatus.APPROVED)

    prev = task.status
    task.status = TaskStatus.APPROVED
    task.approved_by = user_id
    task.approved_at = datetime.now(timezone.utc)

    _log_transition(
        db, task, from_status=prev, to_status=TaskStatus.APPROVED,
        actor=f"user:{user_id}",
    )
    db.commit()
    db.refresh(task)
    return task


def reject_task(
    db: Session,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str = "",
) -> Task:
    """PENDING_APPROVAL → REJECTED."""
    task = _get_task(db, task_id)
    _assert_transition(task.status, TaskStatus.REJECTED)

    prev = task.status
    task.status = TaskStatus.REJECTED
    task.approved_by = user_id       # reuse: approver field covers rejecter too
    task.approved_at = datetime.now(timezone.utc)
    task.result = {"rejected_reason": reason}

    _log_transition(
        db, task, from_status=prev, to_status=TaskStatus.REJECTED,
        actor=f"user:{user_id}", extra={"reason": reason},
    )
    db.commit()
    db.refresh(task)
    return task


def cancel_task(
    db: Session,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str = "",
) -> Task:
    """Any non-terminal status → CANCELLED."""
    task = _get_task(db, task_id)
    _assert_transition(task.status, TaskStatus.CANCELLED)

    prev = task.status
    task.status = TaskStatus.CANCELLED
    task.result = {"cancelled_reason": reason}

    _log_transition(
        db, task, from_status=prev, to_status=TaskStatus.CANCELLED,
        actor=f"user:{user_id}", extra={"reason": reason},
    )
    db.commit()
    db.refresh(task)
    return task


def mark_dispatched(db: Session, task_id: uuid.UUID, actor: str = "system") -> Task:
    """APPROVED → DISPATCHED. Called by the dispatch service."""
    task = _get_task(db, task_id)
    _assert_transition(task.status, TaskStatus.DISPATCHED)

    prev = task.status
    task.status = TaskStatus.DISPATCHED
    task.dispatched_at = datetime.now(timezone.utc)

    _log_transition(
        db, task, from_status=prev, to_status=TaskStatus.DISPATCHED, actor=actor,
    )
    db.commit()
    db.refresh(task)
    return task


def mark_acked(
    db: Session,
    task_id: uuid.UUID,
    response: dict | None = None,
) -> Task:
    """DISPATCHED → ACKED. Called when the device confirms receipt."""
    task = _get_task(db, task_id)
    _assert_transition(task.status, TaskStatus.ACKED)

    prev = task.status
    task.status = TaskStatus.ACKED
    task.acked_at = datetime.now(timezone.utc)
    if response is not None:
        task.result = response

    _log_transition(
        db, task, from_status=prev, to_status=TaskStatus.ACKED, actor="device",
    )
    db.commit()
    db.refresh(task)
    return task


def mark_done(db: Session, task_id: uuid.UUID, result: dict | None = None) -> Task:
    """ACKED → DONE."""
    task = _get_task(db, task_id)
    _assert_transition(task.status, TaskStatus.DONE)

    prev = task.status
    task.status = TaskStatus.DONE
    task.completed_at = datetime.now(timezone.utc)
    if result is not None:
        task.result = result

    _log_transition(
        db, task, from_status=prev, to_status=TaskStatus.DONE, actor="system",
    )
    db.commit()
    db.refresh(task)
    return task


def mark_failed(db: Session, task_id: uuid.UUID, error: str) -> Task:
    """DISPATCHED or ACKED → FAILED."""
    task = _get_task(db, task_id)
    _assert_transition(task.status, TaskStatus.FAILED)

    prev = task.status
    task.status = TaskStatus.FAILED
    task.completed_at = datetime.now(timezone.utc)
    task.result = {"error": error}

    _log_transition(
        db, task, from_status=prev, to_status=TaskStatus.FAILED,
        actor="system", extra={"error": error},
    )
    db.commit()
    db.refresh(task)
    return task