"""
Ack consumer — listens for device acks and updates task state.

Subscribes to agritech/+/plot/+/ack. On each ack:
  - Success: task DISPATCHED → ACKED → DONE
  - Failure: task DISPATCHED → FAILED
  - Also updates the actuator_command row with the response

Idempotent: if a task is already in a terminal or already-acked state,
the message is skipped with a log line.

Usage:
    ./py.bat -m app.workers.mqtt_ack_consumer
"""
import json
from datetime import datetime, timezone
from uuid import UUID

import paho.mqtt.client as mqtt

from app.core.config import settings
from app.db.models.actuator_command import ActuatorCommand
from app.db.models.task import Task, TaskStatus
from app.db.session import SessionLocal
from app.services.task_service import (
    IllegalTransition,
    TaskNotFound,
    mark_acked,
    mark_done,
    mark_failed,
)


ACK_TOPIC = "agritech/+/plot/+/ack"

TERMINAL_STATES = {
    TaskStatus.DONE,
    TaskStatus.FAILED,
    TaskStatus.ACKED,
    TaskStatus.REJECTED,
    TaskStatus.CANCELLED,
}


def _handle_ack(payload: dict) -> None:
    task_id_str = payload.get("task_id")
    if not task_id_str:
        print("Ack missing task_id; skipping")
        return
    try:
        task_id = UUID(task_id_str)
    except ValueError:
        print(f"Bad task_id in ack: {task_id_str}")
        return

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task is None:
            print(f"Unknown task {task_id}; skipping")
            return

        if task.status in TERMINAL_STATES:
            print(f"Task {task_id} already in {task.status.value}; skipping")
            return

        # --- Retry if we caught the task before dispatch's commit landed ---
        # A task should be DISPATCHED before we try to mark it ACKED.
        # If it's still APPROVED, the dispatch commit may still be in flight.
        if task.status == TaskStatus.APPROVED:
            import time
            for attempt in range(5):
                time.sleep(0.4)
                db.expire_all()   # force a fresh read from DB
                task = db.get(Task, task_id)
                if task is None:
                    print(f"Task {task_id} vanished during retry; skipping")
                    return
                if task.status != TaskStatus.APPROVED:
                    break

            if task.status == TaskStatus.APPROVED:
                print(
                    f"Task {task_id} still APPROVED after retries — "
                    f"dispatch commit not visible. Skipping ack."
                )
                return

        status = payload.get("status", "done")

        # --- Failure path ---
        if status == "failed":
            error = payload.get("error") or "device reported failure"
            mark_failed(db, task_id, error)
            print(f"Task {task_id} → FAILED ({error})")
            return

        # --- Success path ---
        response = {
            "command_id": payload.get("command_id"),
            "duration_s": payload.get("duration_s"),
            "reported_at": payload.get("reported_at"),
            "result": payload.get("result"),
        }

        # Update the actuator_command row with the ack response
        cmd = (
            db.query(ActuatorCommand)
            .filter(ActuatorCommand.task_id == task_id)
            .first()
        )
        if cmd is not None:
            cmd.acked_at = datetime.now(timezone.utc)
            cmd.response = response
            db.commit()

        mark_acked(db, task_id, response)
        print(f"Task {task_id} → ACKED")

        mark_done(db, task_id, response)
        print(f"Task {task_id} → DONE")

    except (IllegalTransition, TaskNotFound) as e:
        print(f"State error for {task_id}: {e}")
    except Exception as e:
        print(f"Unexpected error handling ack for {task_id}: {e}")
        db.rollback()
    finally:
        db.close()


def main() -> int:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(c, ud, flags, rc, props=None):
        if not rc.is_failure:
            print(f"Connected. Subscribing to {ACK_TOPIC}")
            c.subscribe(ACK_TOPIC, qos=1)
            print("Listening for acks. Press Ctrl+C to stop.\n")
        else:
            print(f"Connect failed: {rc}")

    def on_message(c, ud, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception as e:
            print(f"Malformed ack: {e}")
            return
        print(f"\n--- Ack received on {msg.topic} ---")
        _handle_ack(payload)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopping ack consumer.")
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())