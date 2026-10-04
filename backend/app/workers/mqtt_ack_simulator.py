"""
Ack simulator — pretends to be a device receiving MQTT commands.

Subscribes to agritech/+/plot/+/cmd, waits a configurable delay to
simulate physical execution, then publishes an ack back on
agritech/{tenant}/plot/{plot}/ack.

In production, real devices would do exactly this — the payload format
is the contract between the platform and hardware.

Usage:
    ./py.bat -m app.workers.mqtt_ack_simulator
    ./py.bat -m app.workers.mqtt_ack_simulator --delay 5
    ./py.bat -m app.workers.mqtt_ack_simulator --failure-rate 0.1
"""
import argparse
import json
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from app.core.config import settings


CMD_TOPIC = "agritech/+/plot/+/cmd"


def _ack_topic(tenant_id: str, plot_id: str) -> str:
    return f"agritech/{tenant_id}/plot/{plot_id}/ack"


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate device acks.")
    parser.add_argument(
        "--delay", type=float, default=3.0,
        help="Seconds to wait before sending the ack (simulates execution)",
    )
    parser.add_argument(
        "--failure-rate", type=float, default=0.0,
        help="Fraction of commands that should fail (0.0-1.0)",
    )
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(c, ud, flags, rc, props=None):
        if not rc.is_failure:
            print(f"Connected. Subscribing to {CMD_TOPIC}")
            c.subscribe(CMD_TOPIC, qos=1)
            print(f"Listening for commands. Delay={args.delay}s, "
                  f"FailureRate={args.failure_rate}")
            print("Press Ctrl+C to stop.\n")
        else:
            print(f"Connect failed: {rc}")

    def on_message(c, ud, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception as e:
            print(f"Malformed command: {e}")
            return

        # Extract tenant_id and plot_id from the topic:
        # agritech/{tenant}/plot/{plot}/cmd
        parts = msg.topic.split("/")
        if len(parts) < 5:
            print(f"Unexpected topic structure: {msg.topic}")
            return
        tenant_id, plot_id = parts[1], parts[3]

        task_id = payload.get("task_id")
        tool = payload.get("tool")
        cmd_args = payload.get("args")
        print(f"\n--- Command received ---")
        print(f"  task_id: {task_id}")
        print(f"  tool:    {tool}")
        print(f"  args:    {cmd_args}")
        print(f"  simulating execution for {args.delay}s...")

        time.sleep(args.delay)

        is_failure = random.random() < args.failure_rate
        status = "failed" if is_failure else "done"

        ack_payload = {
            "command_id": payload.get("command_id"),
            "task_id": task_id,
            "idempotency_key": payload.get("idempotency_key"),
            "status": status,
            "duration_s": args.delay,
            "reported_at": datetime.now(timezone.utc).isoformat(),
            "result": None if is_failure else {
                "tool": tool,
                "success": True,
            },
            "error": "Simulated device failure" if is_failure else None,
        }

        ack_topic = _ack_topic(tenant_id, plot_id)
        c.publish(ack_topic, json.dumps(ack_payload), qos=1)
        print(f"  → ack published to {ack_topic} (status={status})")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopping ack simulator.")
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())