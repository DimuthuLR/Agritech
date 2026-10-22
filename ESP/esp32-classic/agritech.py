# ============================================================
# AgriTech — Main device loop
#
# On boot:
#   1. 3-second interrupt window
#   2. Ensure WiFi is connected
#   3. Ensure device is registered (idempotent)
#   4. Start MQTT listener
#   5. Loop forever:
#        - every 15s: read sensors, send readings
#        - every 60s: send heartbeat
#        - every 1s:   check for incoming MQTT commands
# ============================================================

import time
import gc
import machine

import wifi
import register
import sensors
import signed_api
import api
import mqtt_client
import relays


READING_INTERVAL_SEC = 15
HEARTBEAT_INTERVAL_SEC = 60
FIRMWARE_VERSION = "1.0.0"

BOOT_TIME = time.time()


def _free_heap_kb():
    return gc.mem_free() // 1024


def _send_readings():
    readings = sensors.read_readings()
    for metric, value in readings.items():
        body = {"metric": metric, "value": value}
        try:
            signed_api.post_signed("/sensor/readings", body)
            print(f"  [{metric}] {value} → OK")
        except api.ApiError as e:
            print(f"  [{metric}] FAILED: {e}")


def _send_heartbeat():
    body = {
        "uptime_sec": int(time.time() - BOOT_TIME),
        "free_heap_kb": _free_heap_kb(),
        "rssi_dbm": wifi.get_rssi() or -100,
        "battery_v": sensors.get_battery_voltage(),
        "fw_version": FIRMWARE_VERSION,
        "ts": int(time.time()),
    }
    try:
        signed_api.post_signed("/iot/heartbeat", body)
        print(f"  [heartbeat] OK  heap={body['free_heap_kb']}kB  "
              f"rssi={body['rssi_dbm']}dBm  uptime={body['uptime_sec']}s")
    except api.ApiError as e:
        print(f"  [heartbeat] FAILED: {e}")


def main():
    print("Ctrl+C in the next 3 seconds to interrupt…")
    time.sleep(3)

    print("=" * 50)
    print(f"🌱 AgriTech Device — fw {FIRMWARE_VERSION}")
    print("=" * 50)

    # 1. WiFi
    if not wifi.connect():
        print("❌ WiFi failed — aborting")
        return

    # 2. Registration (idempotent)
    try:
        did = register.register()
        print(f"[main] device_id: {did}")
    except RuntimeError as e:
        print(f"❌ Registration failed: {e}")
        return

    # 3. MQTT listener
    try:
        mqtt = mqtt_client.DeviceMQTT()
        mqtt.ensure_connected()
    except RuntimeError as e:
        print(f"❌ MQTT init failed: {e}")
        return

    print("[main] Entering loop. Interrupt with Ctrl+C.")
    print()

    last_reading = 0
    last_heartbeat = 0

    while True:
        try:
            now = time.time()

            # Process incoming MQTT commands (fast — returns immediately if none)
            mqtt.check()
            
                        # Tick relay timers (non-blocking; auto-off on expiry)

            relays.get().tick()

            if now - last_reading >= READING_INTERVAL_SEC:
                _send_readings()
                last_reading = now

            if now - last_heartbeat >= HEARTBEAT_INTERVAL_SEC:
                _send_heartbeat()
                last_heartbeat = now

            time.sleep(1)

        except KeyboardInterrupt:
            print("\n[main] Interrupted by user")
            break

        except Exception as e:
            print(f"[main] Loop error: {type(e).__name__}: {e}")
            time.sleep(5)

    print("[main] Stopped")


if __name__ == "__main__":
    main()