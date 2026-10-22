# ============================================================
# AgriTech — Sensor Reader
#
# Currently returns SIMULATED values with realistic physics.
# To use real hardware, replace the bodies of read_readings()
# and get_battery_voltage() with actual GPIO/ADC code.
#
# Includes a tiny built-in PRNG so we don't depend on
# MicroPython's random module (which varies across builds).
# ============================================================

import time
import math


class _TinyRandom:
    """
    Linear congruential generator. Same family as C's rand().
    Deterministic, so behavior is reproducible across boots.
    """

    def __init__(self, seed=42):
        self.state = seed & 0xFFFFFFFF

    def next(self):
        # Numerical Recipes LCG constants
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state / 0xFFFFFFFF   # 0.0 <= x < 1.0

    def uniform(self, a, b):
        return a + (b - a) * self.next()


class _SimulatedSensors:
    def __init__(self, seed=42):
        self.rng = _TinyRandom(seed)
        self.soil_moisture = 0.55 + self.rng.uniform(-0.05, 0.05)
        self.battery_v = 4.15 + self.rng.uniform(-0.05, 0.05)
        self._last_tick = time.time()

    def _tick(self, dt_sec):
        now = time.time()
        hour = (now % 86400) / 3600.0
        tod = hour / 24.0

        temp_c = 27.0 + 5.0 * math.sin(2 * math.pi * (tod - 0.33))
        temp_c += self.rng.uniform(-0.3, 0.3)

        humidity = 0.60 - 0.25 * math.sin(2 * math.pi * (tod - 0.33))
        humidity += self.rng.uniform(-0.02, 0.02)
        humidity = max(0.25, min(0.95, humidity))

        self.soil_moisture -= 0.005 * (dt_sec / 15.0)
        if self.rng.next() < 0.005:
            self.soil_moisture += self.rng.uniform(0.10, 0.20)
        self.soil_moisture = max(0.05, min(0.95, self.soil_moisture))

        self.battery_v -= 0.00005 * (dt_sec / 15.0)
        if self.rng.next() < 0.01:
            self.battery_v = min(4.20, self.battery_v + 0.02)

        return {
            "soil_moisture": round(self.soil_moisture, 3),
            "temperature": round(temp_c, 2),
            "humidity": round(humidity, 3),
        }


_sim = _SimulatedSensors()


def read_readings():
    """Return a dict of {metric_name: value} for the readings endpoint."""
    now = time.time()
    dt = now - _sim._last_tick
    _sim._last_tick = now
    return _sim._tick(dt)


def get_battery_voltage():
    """Return battery voltage in volts for the heartbeat."""
    _sim._tick(0)
    return round(_sim.battery_v, 2)