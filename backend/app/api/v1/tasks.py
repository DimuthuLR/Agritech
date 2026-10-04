"""
Task endpoints — tenant-scoped read, plus approve/reject transitions.

State transitions delegate to task_service, which enforces the state
machine. Every transition writes to audit_log automatically.

Endpoints:
    GET    /tasks              — list (optionally filtered by plot)
    GET    /tasks/{id}         — fetch one
    POST   /tasks/{id}/approve — pending_approval → approved
    POST   /tasks/{id}/reject  — pending_approval → rejected
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_tenant_role
from app.db.models.task import Task, TaskStatus
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.task import TaskRead, TaskReject
from app.services.task_service import (
    IllegalTransition,
    TaskNotFound,
    approve_task,
    reject_task,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TaskRead])
def list_tasks(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    plot_id: uuid.UUID | None = None,
    status_filter: TaskStatus | None = None,
    skip: int = 0,
    limit: int = 50,
):
    """List tasks for the caller's tenant, newest first."""
    q = db.query(Task).filter(Task.tenant_id == user.tenant_id)

    if plot_id is not None:
        q = q.filter(Task.plot_id == plot_id)
    if status_filter is not None:
        q = q.filter(Task.status == status_filter)

    return (
        q.order_by(Task.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Fetch one task by ID. 404 if not in caller's tenant."""
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.tenant_id == user.tenant_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

@router.post("/{task_id}/approve", response_model=TaskRead)
def approve(
    task_id: uuid.UUID,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    """
    Approve a pending task. Only OPERATOR or above can approve.
    Enforces status = 'pending_approval'.
    """
    # Tenant ownership check before delegating to task_service
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.tenant_id == user.tenant_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        return approve_task(db, task_id, user.id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail="Task not found")
    except IllegalTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{task_id}/reject", response_model=TaskRead)
def reject(
    task_id: uuid.UUID,
    payload: TaskReject,
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    """
    Reject a pending task with a reason. Reason is required for audit.
    """
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.tenant_id == user.tenant_id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        return reject_task(db, task_id, user.id, payload.reason)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail="Task not found")
    except IllegalTransition as e:
        raise HTTPException(status_code=409, detail=str(e))