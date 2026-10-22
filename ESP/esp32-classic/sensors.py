# ============================================================
# AgriTech — Real sensor reader (classic ESP32)
# DHT11 on GPIO 4, capacitive soil moisture on GPIO 34
# ============================================================

import time
import dht
from machine import Pin, ADC

DHT_PIN = 4
SOIL_PIN = 34

# Calibration (adjust after seeing live readings)
RAW_DRY = 3000    # raw ADC value when probe is dry
RAW_WET = 700     # raw ADC value when probe is in water

_dht = dht.DHT11(Pin(DHT_PIN))

_soil_adc = ADC(Pin(SOIL_PIN))
_soil_adc.atten(ADC.ATTN_11DB)
_soil_adc.width(ADC.WIDTH_12BIT)

_last_dht_read = 0
_last_dht_value = (25.0, 0.5)


def _read_dht():
    global _last_dht_read, _last_dht_value
    now = time.time()
    if now - _last_dht_read < 2:
        return _last_dht_value
    try:
        _dht.measure()
        t = _dht.temperature()
        h = _dht.humidity()
        _last_dht_value = (float(t), float(h) / 100.0)
        _last_dht_read = now
    except OSError as e:
        print("[sensors] DHT11 read failed: {}".format(e))
    return _last_dht_value


def _read_soil():
    raw = _soil_adc.read()
    span = RAW_DRY - RAW_WET
    if span <= 0:
        return 0.0
    m = (RAW_DRY - raw) / span
    if m < 0.0: m = 0.0
    if m > 1.0: m = 1.0
    return m


def read_readings():
    temp_c, humidity_01 = _read_dht()
    soil = _read_soil()
    return {
        "soil_moisture": round(soil, 3),
        "temperature": round(temp_c, 1),
        "humidity": round(humidity_01, 3),
    }


def get_battery_voltage():
    return None   # not wired yet