"""
IoT device simulator.

Registers fake devices with the server, then runs them in parallel
threads. Each device:

  - Sends sensor readings via HTTP POST (HMAC-signed)
  - Sends heartbeats every 60 seconds (HMAC-signed)
  - Subscribes to MQTT commands and acks them
  - Models realistic sensor physics (not just random values)

Usage:

  # 1. Create N devices, using the SAME claim code for the first
  #    (server rejects re-use). Actually: one claim code per device.
  py.bat scripts/simulate_devices.py spawn 5 --tenant demo-farm

  # 2. Run all devices found in simulator_devices/
  py.bat scripts/simulate_devices.py run

  # 3. Delete all saved devices (for a clean slate)
  py.bat scripts/simulate_devices.py reset
"""
import argparse
import hashlib
import hmac as hmac_lib
import json
import math
import random
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import paho.mqtt.client as mqtt
import requests
from sqlalchemy.orm import Session

from app.db.models.device_claim_code import DeviceClaimCode
from app.db.models.tenant import Tenant
from app.db.session import SessionLocal
from app.services.iot_service import generate_claim_code


# =========================================================================
# Configuration
# =========================================================================

SERVER = "http://127.0.0.1:8000/api/v1"
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883

STATE_DIR = Path(__file__).parent.parent / "simulator_devices"

# Timing (seconds)
READING_INTERVAL = 15          # send a reading every 15s
HEARTBEAT_INTERVAL = 60        # heartbeat every 60s
COMMAND_TIMEOUT = 30           # ack must arrive within 30s (server side)


# =========================================================================
# Sensor models — realistic values instead of random noise
# =========================================================================

class SensorModel:
    """
    Deterministic-ish model for a single device's sensors.

    Tracks internal state so values change smoothly, the way real
    sensors do. Temperature follows a 24h sine wave; soil moisture
    decays slowly and jumps when 'irrigation' fires.
    """

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.start_time = time.time()
        self.soil_moisture = 0.55 + self.rng.uniform(-0.05, 0.05)
        self.battery_v = 4.15 + self.rng.uniform(-0.05, 0.05)
        self.uptime_sec = 0

    def tick(self, dt_sec: int) -> dict:
        """Advance the simulation by dt_sec seconds and return readings."""
        self.uptime_sec += dt_sec

        # Time-of-day fraction, 0.0 = midnight, 0.5 = noon
        now = datetime.now(timezone.utc)
        hour = now.hour + now.minute / 60 + now.second / 3600
        tod = hour / 24.0

        # Temperature: peak at 14:00, low at 02:00
        temp_c = 27.0 + 5.0 * math.sin(2 * math.pi * (tod - 0.33))
        temp_c += self.rng.uniform(-0.3, 0.3)

        # Humidity: inversely correlated with temperature
        humidity = 0.60 - 0.25 * math.sin(2 * math.pi * (tod - 0.33))
        humidity += self.rng.uniform(-0.02, 0.02)
        humidity = max(0.25, min(0.95, humidity))

        # Soil moisture: slow decay, occasional "irrigation" bump
        # Decay by ~0.005 per reading tick (15s) → ~1.2/hour
        self.soil_moisture -= 0.005 * (dt_sec / 15.0)
        # Random chance of "rain" bump
        if self.rng.random() < 0.005:
            self.soil_moisture += self.rng.uniform(0.10, 0.20)
        self.soil_moisture = max(0.05, min(0.95, self.soil_moisture))

        # Battery: slow drain
        self.battery_v -= 0.00005 * (dt_sec / 15.0)
        # Sometimes recharge (pretend solar panel)
        if self.rng.random() < 0.01:
            self.battery_v = min(4.20, self.battery_v + 0.02)

        return {
            "soil_moisture": round(self.soil_moisture, 3),
            "temperature": round(temp_c, 2),
            "humidity": round(humidity, 3),
            "battery_v": round(self.battery_v, 2),
        }


# =========================================================================
# Device simulator
# =========================================================================

class DeviceSimulator:
    def __init__(self, state: dict):
        self.state = state
        self.device_id = state["device_id"]
        self.serial = state["serial"]
        self.secret = state["hmac_secret"]
        self.sensors = SensorModel(seed=hash(self.serial) & 0xFFFFFFFF)
        self.stop_flag = threading.Event()
        self.mqtt_client: mqtt.Client | None = None
        self.commands_received = 0
        self.commands_acked = 0
        self.readings_sent = 0
        self.readings_failed = 0

    # --- Signing -------------------------------------------------------

    def _sign(self, body: bytes) -> tuple[str, str, str]:
        """Return (serial, timestamp_str, signature_hex)."""
        ts = int(time.time())
        canonical = f"{self.serial}.{ts}.".encode("utf-8") + body
        sig = hmac_lib.new(
            self.secret.encode("utf-8"), canonical, hashlib.sha256
        ).hexdigest()
        return self.serial, str(ts), sig

    # --- HTTP: readings -------------------------------------------------

    def _send_reading(self, metric: str, value: float) -> bool:
        body = json.dumps({
            "metric": metric,
            "value": value,
            "time": datetime.now(timezone.utc).isoformat(),
        }).encode("utf-8")

        serial, ts, sig = self._sign(body)

        try:
            r = requests.post(
                f"{SERVER}/sensor/readings",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Device-Serial": serial,
                    "X-Timestamp": ts,
                    "X-Signature": sig,
                },
                timeout=10,
            )
            if r.status_code == 201:
                self.readings_sent += 1
                return True
            self.readings_failed += 1
            print(f"[{self.serial[:12]}] reading {metric} → "
                  f"{r.status_code} {r.text[:80]}")
            return False
        except Exception as e:
            self.readings_failed += 1
            print(f"[{self.serial[:12]}] reading {metric} failed: {e}")
            return False

    # --- HTTP: heartbeat ------------------------------------------------

    def _send_heartbeat(self, readings: dict) -> None:
        body = json.dumps({
            "uptime_sec": self.sensors.uptime_sec,
            "free_heap_kb": 140 + int(20 * random.random()),
            "rssi_dbm": -60 + int(-20 * random.random()),
            "battery_v": readings["battery_v"],
            "fw_version": self.state["fw_version"],
            "ts": int(time.time()),
        }).encode("utf-8")

        serial, ts, sig = self._sign(body)

        try:
            r = requests.post(
                f"{SERVER}/iot/heartbeat",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Device-Serial": serial,
                    "X-Timestamp": ts,
                    "X-Signature": sig,
                },
                timeout=10,
            )
            if r.status_code != 200:
                print(f"[{self.serial[:12]}] heartbeat → "
                      f"{r.status_code} {r.text[:80]}")
        except Exception as e:
            print(f"[{self.serial[:12]}] heartbeat failed: {e}")

    # --- MQTT: commands -------------------------------------------------

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            topic = f"agra/devices/{self.device_id}/command"
            client.subscribe(topic, qos=1)
            print(f"[{self.serial[:12]}] MQTT connected, subscribed to {topic}")
        else:
            print(f"[{self.serial[:12]}] MQTT connect failed: {reason_code}")

    def _on_mqtt_message(self, client, userdata, msg):
        self.commands_received += 1
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[{self.serial[:12]}] bad command payload: {e}")
            return

        cmd_id = payload.get("cmd_id", "unknown")
        action = payload.get("action", "unknown")
        params = payload.get("params", {})

        print(f"[{self.serial[:12]}] ← command {cmd_id} action={action}")

        # Simulate execution time
        duration_ms = 50 + int(300 * random.random())
        time.sleep(duration_ms / 1000.0)

        # Handle the action — this is where real hardware would drive GPIO
        status = "ok"
        error = None
        try:
            self._execute_action(action, params)
        except Exception as e:
            status = "failed"
            error = str(e)

        # Publish ack
        ack = json.dumps({
            "cmd_id": cmd_id,
            "status": status,
            "executed_at": int(time.time()),
            "duration_ms": duration_ms,
            "error": error,
        })
        client.publish(
            f"agra/devices/{self.device_id}/ack",
            ack, qos=1,
        )
        self.commands_acked += 1
        print(f"[{self.serial[:12]}] → ack {cmd_id} status={status}")

    def _execute_action(self, action: str, params: dict) -> None:
        """Simulate the physical action. Real hardware would drive GPIO here."""
        if action == "irrigation.start":
            # Bump soil moisture — as if a real pump ran
            duration_sec = params.get("duration_sec", 60)
            self.sensors.soil_moisture += 0.10
            self.sensors.soil_moisture = min(0.95, self.sensors.soil_moisture)
            time.sleep(min(2.0, duration_sec / 60.0))  # short sim delay
        elif action == "irrigation.stop":
            pass
        elif action == "relay.pulse":
            time.sleep(0.5)
        elif action == "reboot":
            self.sensors.uptime_sec = 0
        else:
            raise ValueError(f"unknown action {action!r}")

    # --- Main loop ------------------------------------------------------

    def run(self) -> None:
        print(f"[{self.serial[:12]}] simulator started")

        # Start MQTT in its own thread
        mqtt_thread = threading.Thread(
            target=self._mqtt_loop, daemon=True
        )
        mqtt_thread.start()

        # Timers
        last_reading = 0.0
        last_heartbeat = 0.0
        tick = 0

        try:
            while not self.stop_flag.is_set():
                now = time.time()

                if now - last_reading >= READING_INTERVAL:
                    readings = self.sensors.tick(READING_INTERVAL)
                    for metric in ("soil_moisture", "temperature", "humidity"):
                        self._send_reading(metric, readings[metric])
                    last_reading = now
                    tick += 1

                    if tick % 20 == 0:  # log every ~5 min
                        print(f"[{self.serial[:12]}] "
                              f"sent={self.readings_sent} "
                              f"failed={self.readings_failed} "
                              f"cmds={self.commands_received}")

                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    readings = self.sensors.tick(0)
                    self._send_heartbeat(readings)
                    last_heartbeat = now

                self.stop_flag.wait(timeout=1.0)
        finally:
            if self.mqtt_client:
                try:
                    self.mqtt_client.disconnect()
                except Exception:
                    pass
            print(f"[{self.serial[:12]}] simulator stopped")

    def _mqtt_loop(self) -> None:
        client = mqtt.Client(
            client_id=f"sim-{self.device_id[:12]}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        client.on_connect = self._on_mqtt_connect
        client.on_message = self._on_mqtt_message
        self.mqtt_client = client

        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_forever()
        except Exception as e:
            print(f"[{self.serial[:12]}] MQTT loop error: {e}")

    def stop(self) -> None:
        self.stop_flag.set()


# =========================================================================
# Device state persistence
# =========================================================================

def _device_file(serial: str) -> Path:
    safe = serial.replace(":", "-")
    return STATE_DIR / f"{safe}.json"


def save_device(state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    _device_file(state["serial"]).write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )


def load_devices() -> list[dict]:
    if not STATE_DIR.exists():
        return []
    devices = []
    for path in sorted(STATE_DIR.glob("*.json")):
        try:
            devices.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"Skipping {path.name}: {e}")
    return devices


# =========================================================================
# Commands
# =========================================================================

def _make_fake_mac(i: int) -> str:
    """Deterministic fake MAC for the Nth simulator."""
    return f"02:00:00:{i:02X}:{(i*7)%256:02X}:{(i*13)%256:02X}"


def _db_create_claim_codes(tenant_slug: str, count: int) -> list[str]:
    """Create `count` claim codes for the given tenant; return them."""
    db: Session = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            print(f"Tenant '{tenant_slug}' not found.")
            sys.exit(1)

        codes = []
        from datetime import timedelta
        for _ in range(count):
            code = generate_claim_code()
            db.add(DeviceClaimCode(
                tenant_id=tenant.id,
                code=code,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            ))
            codes.append(code)
        db.commit()
        return codes
    finally:
        db.close()


def cmd_spawn(args) -> None:
    """Register N devices with the server."""
    print(f"Spawning {args.count} simulated devices for tenant {args.tenant}…")
    print("Generating claim codes…")
    codes = _db_create_claim_codes(args.tenant, args.count)

    for i, code in enumerate(codes, start=1):
        mac = _make_fake_mac(int(time.time()) % 10000 + i)
        body = {
            "mac": mac,
            "hw_version": "simulator-v1.0",
            "fw_version": "0.1.0",
            "chip": "simulator",
            "claim_code": code,
        }
        try:
            r = requests.post(
                f"{SERVER}/iot/register",
                json=body,
                timeout=10,
            )
        except Exception as e:
            print(f"  [{i}] register failed: {e}")
            continue

        if r.status_code != 201:
            print(f"  [{i}] register → {r.status_code} {r.text[:80]}")
            continue

        resp = r.json()
        state = {
            "device_id": resp["device_id"],
            "serial": resp["device_serial"],
            "hmac_secret": resp["hmac_secret"],
            "hw_version": "simulator-v1.0",
            "fw_version": "0.1.0",
            "chip": "simulator",
            "created_at": resp["provisioned_at"],
        }
        save_device(state)
        print(f"  [{i}] ✓ {state['serial']} → {state['device_id'][:12]}")

    print(f"\nDone. Devices saved to {STATE_DIR}")


def cmd_run(args) -> None:
    """Run all saved devices."""
    states = load_devices()
    if not states:
        print(f"No devices found in {STATE_DIR}. Run 'spawn' first.")
        sys.exit(1)

    print(f"Starting {len(states)} simulated devices…")
    print("Press Ctrl+C to stop.\n")

    simulators = [DeviceSimulator(s) for s in states]
    threads = [
        threading.Thread(target=sim.run, daemon=True)
        for sim in simulators
    ]

    # Ctrl+C handler
    def handle_sigint(sig, frame):
        print("\nStopping all devices…")
        for sim in simulators:
            sim.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    for t in threads:
        t.start()

    # Keep the main thread alive
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        for sim in simulators:
            sim.stop()
        time.sleep(1)

    print("All devices stopped.")


def cmd_reset(args) -> None:
    """Delete all saved device state files."""
    if not STATE_DIR.exists():
        print("Nothing to reset.")
        return
    files = list(STATE_DIR.glob("*.json"))
    for f in files:
        f.unlink()
    print(f"Deleted {len(files)} device files.")


# =========================================================================
# CLI
# =========================================================================

def main() -> None:
    p = argparse.ArgumentParser(description="IoT device simulator")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("spawn", help="Register N devices with the server")
    sp.add_argument("count", type=int, help="Number of devices")
    sp.add_argument("--tenant", required=True, help="Tenant slug")
    sp.set_defaults(func=cmd_spawn)

    rp = sub.add_parser("run", help="Run all saved devices")
    rp.set_defaults(func=cmd_run)

    rp = sub.add_parser("reset", help="Delete all saved device files")
    rp.set_defaults(func=cmd_reset)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()