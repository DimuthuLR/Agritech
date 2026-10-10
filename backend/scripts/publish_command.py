"""
Manually publish a command to a simulated device.

Used to test the simulator's command handler without needing the
full task-dispatch flow to be wired up yet.

Usage:
    py.bat scripts/publish_command.py <device_id> <action> [json_params]

Examples:
    py.bat scripts/publish_command.py d_abc123 irrigation.start '{"duration_sec": 60}'
    py.bat scripts/publish_command.py d_abc123 reboot
"""
import argparse
import json
import secrets
import sys
import time

import paho.mqtt.client as mqtt


MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("device_id")
    p.add_argument("action")
    p.add_argument("params_json", nargs="?", default="{}")
    args = p.parse_args()

    try:
        params = json.loads(args.params_json)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON params: {e}")
        sys.exit(1)

    cmd_id = "c_" + secrets.token_hex(6)
    payload = json.dumps({
        "cmd_id": cmd_id,
        "action": args.action,
        "params": params,
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + 300,
    })

    client = mqtt.Client(
        client_id="cmd-publisher",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)

    topic = f"agra/devices/{args.device_id}/command"
    client.publish(topic, payload, qos=1)
    client.disconnect()

    print(f"Published to {topic}")
    print(f"  cmd_id: {cmd_id}")
    print(f"  action: {args.action}")
    print(f"  params: {params}")


if __name__ == "__main__":
    main()