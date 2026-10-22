# ============================================================
# AgriTech — HL-52S relay controller with non-blocking timers
#
# Wired:
#   IN1 → GPIO 5   (pump)
#   IN2 → GPIO 18  (valve)
#
# Active-LOW: value(0) = relay ON, value(1) = relay OFF.
#
# Firmware-enforced maximums (safety):
#   Any duration_sec > MAX_PUMP_SEC is clamped.
#   Any duration_sec > MAX_VALVE_SEC is clamped.
# This is a hardware-level guarantee independent of any server logic.
# ============================================================

import time
from machine import Pin


RELAY_1_PIN = 5
RELAY_2_PIN = 18

MAX_PUMP_SEC = 120
MAX_VALVE_SEC = 300


class Relays:
    def __init__(self):
        self.pump = Pin(RELAY_1_PIN, Pin.OUT, value=1)
        self.valve = Pin(RELAY_2_PIN, Pin.OUT, value=1)
        self.pump_on_until = 0
        self.valve_on_until = 0

    # --- Immediate control (no timer) ---

    def pump_on(self):
        self.pump.value(0)

    def pump_off(self):
        self.pump.value(1)
        self.pump_on_until = 0

    def valve_on(self):
        self.valve.value(0)

    def valve_off(self):
        self.valve.value(1)
        self.valve_on_until = 0

    # --- Timed control (non-blocking) ---

    def pump_on_for(self, seconds):
        seconds = int(seconds)
        if seconds <= 0:
            self.pump_off()
            return
        if seconds > MAX_PUMP_SEC:
            print("[relays] pump duration clamped to {}s".format(MAX_PUMP_SEC))
            seconds = MAX_PUMP_SEC
        self.pump.value(0)
        self.pump_on_until = time.time() + seconds

    def valve_on_for(self, seconds):
        seconds = int(seconds)
        if seconds <= 0:
            self.valve_off()
            return
        if seconds > MAX_VALVE_SEC:
            print("[relays] valve duration clamped to {}s".format(MAX_VALVE_SEC))
            seconds = MAX_VALVE_SEC
        self.valve.value(0)
        self.valve_on_until = time.time() + seconds

    # --- Called from the main loop every ~1 second ---

    def tick(self):
        """Turn off any relay whose timer has expired. Non-blocking."""
        now = time.time()
        if self.pump_on_until and now >= self.pump_on_until:
            print("[relays] pump auto-off (timer expired)")
            self.pump_off()
        if self.valve_on_until and now >= self.valve_on_until:
            print("[relays] valve auto-off (timer expired)")
            self.valve_off()

    def all_off(self):
        self.pump.value(1)
        self.valve.value(1)
        self.pump_on_until = 0
        self.valve_on_until = 0

    # --- Status (for future use) ---

    def status(self):
        return {
            "pump_on": self.pump.value() == 0,
            "valve_on": self.valve.value() == 0,
            "pump_remaining_s": max(0, int(self.pump_on_until - time.time())) if self.pump_on_until else 0,
            "valve_remaining_s": max(0, int(self.valve_on_until - time.time())) if self.valve_on_until else 0,
        }


_instance = None


def get():
    global _instance
    if _instance is None:
        _instance = Relays()
    return _instance