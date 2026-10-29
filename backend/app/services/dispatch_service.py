"""
Dispatch service — sends approved tasks to hardware via HTTP Long Polling.

Design principles:
- Idempotency first: the same task_id NEVER results in two commands.
- Persist before broadcast: the actuator_command row is written first, so if
  the process crashes, the next dispatch of the same task sees the existing 
  command and returns it without re-sending.
- Single transaction: task transition + command + audit entries commit together.

Topic structure (replaced MQTT):
- The Hub polls `/iot/command/poll`.
- We push the payload directly into the in-memory `COMMAND_QUEUES`.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.safety.audit import write_audit
from app.db.models.actuator_command import ActuatorCommand
from app.db.models.device import Device
from app.db.models.task import Task, TaskStatus
from app.services.task_service import _assert_transition, _log_transition

# Import the queue we created in iot.py
from app.api.v1.iot import COMMAND_QUEUES

log = logging.getLogger(__name__)


class DispatchError(Exception):
    """Base error for dispatch operations."""


class TaskNotDispatchable(DispatchError):
    """Raised when a task cannot be dispatched in its current state."""


def _map_task_to_action(task: Task) -> str:
    """Map internal task tools to physical C3 actions."""
    if task.tool == "control_irrigation":
        return "irrigation.start"
    elif task.tool == "spray_chemical":
        # For now, assume spray triggers a valve/pump. Adjust based on hardware.
        return "valve.open" 
    return "reboot" # Fallback


def dispatch_task(db: Session, task_id: uuid.UUID) -> ActuatorCommand:
    """
    Dispatch one APPROVED task. Returns the ActuatorCommand record.
    """
    task = db.get(Task, task_id)
    if task is None:
        raise DispatchError(f"Task {task_id} not found")

    # --- Idempotency check: already dispatched? ---
    existing = (
        db.query(ActuatorCommand)
        .filter(ActuatorCommand.task_id == task.id)
        .first()
    )
    if existing is not None:
        log.info(f"Task {task.id} already has command {existing.id}; skipping")
        return existing

    # --- Only APPROVED tasks can be dispatched ---
    if task.status != TaskStatus.APPROVED:
        raise TaskNotDispatchable(
            f"Task {task.id} has status {task.status.value}; "
            f"only APPROVED tasks can be dispatched"
        )

    # --- Find the Gateway (Hub) for this tenant ---
    gateway = (
        db.query(Device)
        .filter(Device.tenant_id == task.tenant_id, Device.kind == 'gateway')
        .first()
    )
    if not gateway:
        raise DispatchError(f"No Gateway found for tenant {task.tenant_id}")

    # --- Build the message for the Hub ---
    command_id = uuid.uuid4()
    action = _map_task_to_action(task)
    
    # The exact payload format the Hub expects
    payload = {
        "action": action,
        "params": task.args or {},
        "cmd_id": str(command_id),
        "target_device_serial": "48:F6:EE:13:A9:90" # In a fully dynamic setup, look this up from DB
    }

    # --- Build the command row ---
    cmd = ActuatorCommand(
        id=command_id,
        tenant_id=task.tenant_id,
        task_id=task.id,
        device_id=task.device_id,
        topic=f"http-poll/{gateway.id}",
        payload=payload,
        idempotency_key=task.idempotency_key,
    )
    db.add(cmd)
    db.flush()

    # --- Transition task to DISPATCHED (audited) ---
    _assert_transition(task.status, TaskStatus.DISPATCHED)
    prev = task.status
    task.status = TaskStatus.DISPATCHED
    task.dispatched_at = datetime.now(timezone.utc)
    _log_transition(db, task, prev, TaskStatus.DISPATCHED, actor="dispatch_service")
    db.flush()

    write_audit(
        db,
        kind="dispatch.sent",
        payload={
            "task_id": str(task.id),
            "command_id": str(command_id),
            "action": action,
            "tool": task.tool,
        },
        actor="dispatch_service",
        tenant_id=task.tenant_id,
        target_type="task",
        target_id=str(task.id),
    )

    # Commit BEFORE adding to queue
    db.commit()
    db.refresh(cmd)

    # --- Push to the in-memory queue for the Hub to poll ---
    str_gateway_id = str(gateway.id)
    if str_gateway_id not in COMMAND_QUEUES:
        COMMAND_QUEUES[str_gateway_id] = []
        
    COMMAND_QUEUES[str_gateway_id].append(payload)
    log.info(f"[Dispatch] Pushed {action} to queue for Hub {gateway.serial}")

    return cmd


def dispatch_all_approved(db: Session) -> list[tuple[uuid.UUID, str]]:
    """
    Dispatch every APPROVED task. Returns a list of (task_id, outcome).
    """
    tasks = (
        db.query(Task)
        .filter(Task.status == TaskStatus.APPROVED)
        .order_by(Task.created_at.asc())
        .all()
    )

    results: list[tuple[uuid.UUID, str]] = []
    for t in tasks:
        try:
            dispatch_task(db, t.id)
            results.append((t.id, "dispatched"))
        except DispatchError as e:
            log.warning(f"Dispatch failed for task {t.id}: {e}")
            results.append((t.id, f"error: {e}"))
    return results