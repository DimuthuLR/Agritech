# ============================================================
# AgriTech — MQTT command listener
#
# Subscribes to agra/devices/{device_id}/command.
# Executes actions (currently simulated) and publishes an ack to
# agra/devices/{device_id}/ack.
#
# Keeps the connection alive by pinging the broker every
# PING_EVERY_N_CHECKS calls to check(). MicroPython's umqtt can be
# unreliable about automatic pings, and a flapping connection
# causes QoS 1 commands to be dropped on reconnect.
# ============================================================

import json
import time
from umqtt.robust import MQTTClient

import storage
import hmac_sign

try:
    from secrets import MQTT_HOST, MQTT_PORT
except ImportError:
    raise RuntimeError("secrets.py missing MQTT_HOST/MQTT_PORT")


MAX_SEEN_COMMANDS = 50
RECONNECT_INTERVAL_SEC = 5
PING_EVERY_N_CHECKS = 20    # 20 * 1s loop = ping every 20 seconds


class DeviceMQTT:
    def __init__(self):
        self.device_id = storage.get_string("device_id")
        if not self.device_id:
            raise RuntimeError(
                "Device not registered. Call register.register() first."
            )

        self.mac = storage.get_string("registered_mac") or "unknown"
        self.topic_command = "agra/devices/{}/command".format(self.device_id)
        self.topic_ack = "agra/devices/{}/ack".format(self.device_id)

        self.client = None
        self.seen_cmd_ids = []
        self.last_connect_attempt = 0
        self.connected = False

        # Ping counter — every N check() calls, send a keepalive ping
        self._check_counter = 0

    # ---- Connection management ----

    def ensure_connected(self):
        if self.connected and self.client is not None:
            return True

        now = time.time()
        if now - self.last_connect_attempt < RECONNECT_INTERVAL_SEC:
            return False
        self.last_connect_attempt = now

        try:
            client_id = "esp32-" + self.mac.replace(":", "")
            self.client = MQTTClient(
                client_id=client_id,
                server=MQTT_HOST,
                port=MQTT_PORT,
                keepalive=60,
            )
            self.client.set_callback(self._on_message)
            self.client.connect()
            self.client.subscribe(self.topic_command.encode(), qos=1)
            self.connected = True
            self._check_counter = 0
            print("[mqtt] Connected, subscribed to {}".format(self.topic_command))
            return True
        except Exception as e:
            print("[mqtt] Connect failed: {}".format(e))
            self.client = None
            self.connected = False
            return False

    # ---- Main-loop hook ----

    def check(self):
        if not self.ensure_connected():
            return

        # Explicit keepalive ping on a fixed counter — does NOT rely on
        # time.time() being correct, which it isn't on this firmware.
        self._check_counter += 1
        if self._check_counter >= PING_EVERY_N_CHECKS:
            print("[mqtt] ping (every {}s)".format(PING_EVERY_N_CHECKS))
            try:
                self.client.ping()
                print("[mqtt]   ping OK")
            except Exception as e:
                print("[mqtt]   ping FAILED: {}".format(e))
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

    # ---- Publish ----

    def publish_ack(self, cmd_id, status, duration_ms, error=None):
        payload = {
            "cmd_id": cmd_id,
            "status": status,
            "executed_at": hmac_sign.unix_now(),
            "duration_ms": duration_ms,
            "error": error,
        }
        try:
            self.client.publish(
                self.topic_ack.encode(),
                json.dumps(payload),
                qos=1,
            )
            print("[mqtt] ack sent: {} {}".format(cmd_id, status))
        except Exception as e:
            print("[mqtt] Failed to send ack: {}".format(e))

    # ---- Incoming message handling ----

    def _remember(self, cmd_id):
        self.seen_cmd_ids.append(cmd_id)
        if len(self.seen_cmd_ids) > MAX_SEEN_COMMANDS:
            self.seen_cmd_ids.pop(0)

    def _already_seen(self, cmd_id):
        return cmd_id in self.seen_cmd_ids

    def _on_message(self, topic, msg):
        topic_str = topic.decode() if isinstance(topic, bytes) else str(topic)
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

        if not cmd_id:
            print("[mqtt] Missing cmd_id, ignoring")
            return

        if self._already_seen(cmd_id):
            print("[mqtt] Duplicate command, ignoring")
            return

        if expires_at and hmac_sign.unix_now() > int(expires_at):
            self._remember(cmd_id)
            self.publish_ack(cmd_id, "rejected", 0, error="expired")
            return

        start_ms = time.ticks_ms()
        status = "ok"
        error = None
        try:
            self._execute_action(action, params)
        except Exception as e:
            status = "failed"
            error = str(e)
            print("[mqtt] Action failed: {}".format(e))

        duration = time.ticks_diff(time.ticks_ms(), start_ms)

        self._remember(cmd_id)
        self.publish_ack(cmd_id, status, duration, error=error)

    def _execute_action(self, action, params):
        """Simulated. Real GPIO in Phase IoT-5'."""
        if action == "irrigation.start":
            duration_sec = params.get("duration_sec", 60)
            print("[mqtt]   → (simulated) pump ON for {}s".format(duration_sec))
            time.sleep(0.3)
        elif action == "irrigation.stop":
            print("[mqtt]   → (simulated) pump OFF")
            time.sleep(0.1)
        elif action == "valve.open":
            print("[mqtt]   → (simulated) valve OPEN")
            time.sleep(0.2)
        elif action == "valve.close":
            print("[mqtt]   → (simulated) valve CLOSE")
            time.sleep(0.1)
        elif action == "relay.pulse":
            print("[mqtt]   → (simulated) relay pulse")
            time.sleep(0.5)
        elif action == "reboot":
            print("[mqtt]   → (simulated) reboot")
        else:
            raise ValueError("unknown action: {}".format(action))