# ============================================================
# AgriTech — MQTT command listener (classic ESP32 with relays)
# ============================================================

import json
import time
from umqtt.robust import MQTTClient

import storage
import hmac_sign
import relays

try:
    from secrets import MQTT_HOST, MQTT_PORT
except ImportError:
    raise RuntimeError("secrets.py missing MQTT_HOST/MQTT_PORT")

MAX_SEEN_COMMANDS = 50
RECONNECT_INTERVAL_SEC = 5
PING_EVERY_N_CHECKS = 20


class DeviceMQTT:
    def __init__(self):
        self.device_id = storage.get_string("device_id")
        if not self.device_id:
            raise RuntimeError("Not registered — call register.register() first.")
        self.mac = storage.get_string("registered_mac") or "unknown"
        self.topic_command = "agra/devices/{}/command".format(self.device_id)
        self.topic_ack = "agra/devices/{}/ack".format(self.device_id)
        self.client = None
        self.seen_cmd_ids = []
        self.last_connect_attempt = 0
        self.connected = False
        self._check_counter = 0

    def ensure_connected(self):
        if self.connected and self.client is not None:
            return True
        now = time.time()
        if now - self.last_connect_attempt < RECONNECT_INTERVAL_SEC:
            return False
        self.last_connect_attempt = now
        try:
            self.client = MQTTClient(
                client_id="esp32-" + self.mac.replace(":", ""),
                server=MQTT_HOST, port=MQTT_PORT, keepalive=60,
            )
            self.client.set_callback(self._on_message)
            self.client.connect()
            self.client.subscribe(self.topic_command.encode(), qos=1)
            self.connected = True
            self._check_counter = 0
            print("[mqtt] Connected to {}".format(self.topic_command))
            return True
        except Exception as e:
            print("[mqtt] Connect failed: {}".format(e))
            self.client = None
            self.connected = False
            return False

    def check(self):
        if not self.ensure_connected():
            return
        self._check_counter += 1
        if self._check_counter >= PING_EVERY_N_CHECKS:
            try:
                self.client.ping()
            except Exception as e:
                print("[mqtt] ping failed: {}".format(e))
                self.connected = False
                self.client = None
                return
            self._check_counter = 0
        try:
            self.client.check_msg()
        except Exception as e:
            print("[mqtt] check_msg failed: {}".format(e))
            self.connected = False
            self.client = None

    def publish_ack(self, cmd_id, status, duration_ms, error=None):
        payload = {
            "cmd_id": cmd_id,
            "status": status,
            "executed_at": hmac_sign.unix_now(),
            "duration_ms": duration_ms,
            "error": error,
        }
        try:
            self.client.publish(self.topic_ack.encode(), json.dumps(payload), qos=1)
            print("[mqtt] ack sent: {} {}".format(cmd_id, status))
        except Exception as e:
            print("[mqtt] ack failed: {}".format(e))

    def _remember(self, cmd_id):
        self.seen_cmd_ids.append(cmd_id)
        if len(self.seen_cmd_ids) > MAX_SEEN_COMMANDS:
            self.seen_cmd_ids.pop(0)

    def _already_seen(self, cmd_id):
        return cmd_id in self.seen_cmd_ids

    def _on_message(self, topic, msg):
        try:
            payload = json.loads(msg.decode("utf-8"))
        except Exception as e:
            print("[mqtt] Bad payload: {}".format(e))
            return
        cmd_id = payload.get("cmd_id", "")
        action = payload.get("action", "")
        params = payload.get("params", {})
        expires_at = payload.get("expires_at", 0)
        print("[mqtt] <- {} action={}".format(cmd_id, action))
        if not cmd_id or self._already_seen(cmd_id):
            return
        if expires_at and hmac_sign.unix_now() > int(expires_at):
            self._remember(cmd_id)
            self.publish_ack(cmd_id, "rejected", 0, error="expired")
            return
        start_ms = time.ticks_ms()
        status, error = "ok", None
        try:
            self._execute_action(action, params)
        except Exception as e:
            status, error = "failed", str(e)
            print("[mqtt] Action failed: {}".format(e))
        duration = time.ticks_diff(time.ticks_ms(), start_ms)
        self._remember(cmd_id)
        self.publish_ack(cmd_id, status, duration, error=error)

    def _execute_action(self, action, params):
        """Non-blocking. Sets timers; the main loop turns relays off."""
        r = relays.get()

        if action == "irrigation.start":
            duration_sec = int(params.get("duration_sec", 60))
            print("[mqtt]   → PUMP ON for {}s (non-blocking)".format(duration_sec))
            r.pump_on_for(duration_sec)

        elif action == "irrigation.stop":
            print("[mqtt]   → PUMP OFF")
            r.pump_off()

        elif action == "valve.open":
            duration_sec = int(params.get("duration_sec", 0))
            if duration_sec > 0:
                print("[mqtt]   → VALVE OPEN for {}s".format(duration_sec))
                r.valve_on_for(duration_sec)
            else:
                print("[mqtt]   → VALVE OPEN (until closed)")
                r.valve_on()

        elif action == "valve.close":
            print("[mqtt]   → VALVE CLOSE")
            r.valve_off()

        elif action == "relay.pulse":
            ms = int(params.get("duration_ms", 500))
            print("[mqtt]   → PUMP pulse {}ms".format(ms))
            r.pump_on()
            time.sleep(ms / 1000.0)
            r.pump_off()

        else:
            raise ValueError("unknown action: {}".format(action))