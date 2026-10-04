"""
Dispatch service — sends approved tasks to hardware via MQTT.

Design principles:
- Idempotency first: the same task_id NEVER results in two MQTT messages.
  We check for an existing actuator_command before publishing.
- Persist before publish: the actuator_command row is written first, so if
  the publish succeeds but the process crashes, the next dispatch of the
  same task sees the existing command and returns it without re-sending.
- Single transaction: task transition + command + audit entries commit
  together. Either everything lands, or nothing does.

Topic structure:
    agritech/{tenant_id}/plot/{plot_id}/cmd       — commands to devices
    agritech/{tenant_id}/plot/{plot_id}/ack       — acks from devices (Phase 6e)
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.safety.audit import write_audit
from app.db.models.actuator_command import ActuatorCommand
from app.db.models.task import Task, TaskStatus
from app.services.task_service import _assert_transition, _log_transition


log = logging.getLogger(__name__)


CMD_TOPIC_TEMPLATE = "agritech/{tenant_id}/plot/{plot_id}/cmd"
ACK_TOPIC_TEMPLATE = "agritech/{tenant_id}/plot/{plot_id}/ack"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DispatchError(Exception):
    """Base error for dispatch operations."""


class TaskNotDispatchable(DispatchError):
    """Raised when a task cannot be dispatched in its current state."""


# ---------------------------------------------------------------------------
# MQTT client (process-lifetime singleton)
# ---------------------------------------------------------------------------

_client: mqtt.Client | None = None


def _get_mqtt_client() -> mqtt.Client:
    """Return a connected MQTT client, connecting on first use."""
    global _client
    if _client is not None:
        return _client

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    except Exception as e:
        raise DispatchError(
            f"MQTT broker unreachable at "
            f"{settings.mqtt_host}:{settings.mqtt_port}: {e}"
        )

    client.loop_start()   # background thread for network I/O
    _client = client
    return client


def disconnect_mqtt() -> None:
    """Call at script exit for a clean shutdown."""
    global _client
    if _client is not None:
        try:
            _client.loop_stop()
            _client.disconnect()
        except Exception:
            pass
        _client = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_topic(task: Task) -> str:
    return CMD_TOPIC_TEMPLATE.format(
        tenant_id=task.tenant_id,
        plot_id=task.plot_id,
    )


def _build_payload(task: Task, command_id: uuid.UUID) -> dict:
    return {
        "command_id": str(command_id),
        "task_id": str(task.id),
        "idempotency_key": str(task.idempotency_key),
        "tool": task.tool,
        "args": task.args,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def dispatch_task(db: Session, task_id: uuid.UUID) -> ActuatorCommand:
    """
    Dispatch one APPROVED task. Returns the ActuatorCommand record.

    Idempotent: if an actuator_command already exists for this task, that
    record is returned and no MQTT message is sent.

    Raises DispatchError on MQTT failure, TaskNotDispatchable if the task
    is not in APPROVED state.
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

    # --- Build the message ---
    command_id = uuid.uuid4()
    topic = _build_topic(task)
    payload = _build_payload(task, command_id)

    # --- Build the command row ---
    cmd = ActuatorCommand(
        id=command_id,
        tenant_id=task.tenant_id,
        task_id=task.id,
        device_id=task.device_id,
        topic=topic,
        payload=payload,
        idempotency_key=task.idempotency_key,
    )
    db.add(cmd)
    db.flush()

    # --- Transition task to DISPATCHED (audited) ---
    # This MUST land in the DB before we publish MQTT, otherwise a fast
    # ack could reach the consumer before the task's dispatched status
    # is visible. Committing first eliminates the race.
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
            "topic": topic,
            "tool": task.tool,
            "args": task.args,
        },
        actor="dispatch_service",
        tenant_id=task.tenant_id,
        target_type="task",
        target_id=str(task.id),
    )

    # Commit BEFORE publishing so the consumer sees DISPATCHED if it
    # processes an ack immediately after.
    db.commit()
    db.refresh(cmd)

    # --- Now publish to MQTT ---
    try:
        client = _get_mqtt_client()
        info = client.publish(topic, json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=5.0)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            # Publish failed AFTER commit. The command is recorded but no
            # message went out. Log and raise so the caller can decide.
            log.error(
                f"MQTT publish failed rc={info.rc} for task {task.id}; "
                f"command {cmd.id} is recorded but not on the wire"
            )
            raise DispatchError(f"publish rc={info.rc} (command recorded, not sent)")
    except Exception as e:
        if isinstance(e, DispatchError):
            raise
        log.error(f"MQTT publish exception for task {task.id}: {e}")
        raise DispatchError(f"MQTT publish failed: {e}") from e

    return cmd


def dispatch_all_approved(db: Session) -> list[tuple[uuid.UUID, str]]:
    """
    Dispatch every APPROVED task. Returns a list of (task_id, outcome)
    where outcome is either 'dispatched' or 'error: <reason>'.
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