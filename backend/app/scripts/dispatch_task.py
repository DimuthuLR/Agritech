"""
Dispatch one approved task to hardware via MQTT.

Usage:
    ./py.bat -m app.scripts.dispatch_task <task-uuid>
"""
import argparse
import json
import sys
from uuid import UUID

from app.db.session import SessionLocal
from app.services.dispatch_service import (
    DispatchError,
    TaskNotDispatchable,
    disconnect_mqtt,
    dispatch_task,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Dispatch one task.")
    p.add_argument("task_id", help="Task UUID")
    args = p.parse_args()

    try:
        task_id = UUID(args.task_id)
    except ValueError:
        print(f"ERROR: invalid UUID {args.task_id!r}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        cmd = dispatch_task(db, task_id)
        print("Dispatched:")
        print(f"  command_id: {cmd.id}")
        print(f"  task_id:    {cmd.task_id}")
        print(f"  topic:      {cmd.topic}")
        print(f"  payload:    {json.dumps(cmd.payload, indent=2)}")
        return 0
    except TaskNotDispatchable as e:
        print(f"ERROR (not dispatchable): {e}", file=sys.stderr)
        return 2
    except DispatchError as e:
        print(f"ERROR (dispatch failed): {e}", file=sys.stderr)
        return 3
    finally:
        db.close()
        disconnect_mqtt()


if __name__ == "__main__":
    sys.exit(main())